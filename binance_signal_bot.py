# -*- coding: utf-8 -*-

import sys
import time
import asyncio
import traceback
from datetime import datetime

import pandas as pd
import numpy as np
import telegram
import ccxt


def _run_async(coro):
    """Helper to run a single async call synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=30)
    else:
        return asyncio.run(coro)

CONFIG = {
    "TELEGRAM": {
        "BOT_TOKEN": "SEU_BOT_TOKEN",
        "CHAT_ID": "SEU_CHAT_ID",
    },
    "MARKET_SELECTION": {
        "QUOTE_CURRENCY": "USDT",
        "TOP_N": 3,
        "MIN_QUOTE_VOLUME_USDT": 500000,
        "MAX_SPREAD_PCT": 1.0,
        "MAX_ABS_PERCENTAGE": 100.0,
        "VOLATILITY_WEIGHT": 0.45,
        "VOLUME_WEIGHT": 0.30,
        "SPREAD_WEIGHT": 0.25,
    },
    "STRATEGY_CONFIG": {
        "timeframe": "5m",
        "amplitude": 2,
        "ATR_Target_Multipliers": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10],
    },
    "FILTER_CONFIG": {
        "enable": True,
        "timeframe": "15m",
        "amplitude": 2,
    },
    "SIGNAL_MESSAGE": {
        "buy_title": "SINAL DE COMPRA | BINANCE FUTURES",
        "sell_title": "SINAL DE VENDA | BINANCE FUTURES",
        "initial_footer": (
            "\n\nPonto de Entrada: {price:,.8f}\n"
            "Volatilidade (ATR): {atr_percent:.2f}%\n\n"
            "@OrochiiFX"
        ),
        "update_reply": (
            "ALVO {target_number} ATINGIDO! ({target_multiplier:.1f}x ATR)\n\n"
            "Preco Atual: {current_price:,.8f}\n"
            "Lucro Total: +{total_percentage:.2f}%\n\n"
            "@OrochiiFX"
        ),
    },
    "CANDLE_LIMIT": 200,
    "LOOP_INTERVAL_SECONDS": 60,
}


class SignalSentryBinance:
    def __init__(self, config):
        self.config = config
        self.exchange = None
        self.bot = None
        self.monitored_markets = []
        self.asset_states = {}

    def _connect(self):
        try:
            self.exchange = ccxt.binance({
                'options': {'defaultType': 'future'},
            })
            self.exchange.load_markets(True)
            print("Conectado a API publica da Binance Futures!")

            self.bot = telegram.Bot(token=self.config['TELEGRAM']['BOT_TOKEN'])
            print("Conectado ao Telegram!")
        except Exception as e:
            print(f"ERRO nas conexoes: {e}")
            traceback.print_exc()
            sys.exit()

    def _find_top_ranked_assets(self):
        print("\nBuscando melhores ativos da Binance Futures (Volatilidade + Volume + Spread)...")
        try:
            if not self.exchange.markets:
                self.exchange.load_markets(True)

            ms = self.config['MARKET_SELECTION']
            quote = ms['QUOTE_CURRENCY']
            min_vol = ms.get('MIN_QUOTE_VOLUME_USDT', 500000)
            max_spread = ms.get('MAX_SPREAD_PCT', 1.0)
            max_abs_pct = ms.get('MAX_ABS_PERCENTAGE', 100.0)

            swap_symbols = [
                symbol
                for symbol, market in self.exchange.markets.items()
                if (market.get('type') == 'swap'
                    and market.get('quote') == quote
                    and market.get('active')
                    and market.get('linear'))
            ]

            if not swap_symbols:
                print("Nenhum contrato perpétuo USDT-M encontrado.")
                sys.exit()

            print(f"   {len(swap_symbols)} contratos perpétuos. Carregando tickers...")

            all_tickers = self.exchange.fetch_tickers()

            book_tickers = {}
            try:
                raw_books = self.exchange.fapiPublicGetTickerBookTicker()
                book_tickers = {
                    bt['symbol']: {'bid': float(bt['bidPrice']), 'ask': float(bt['askPrice'])}
                    for bt in raw_books
                }
                print(f"   Book tickers carregados para {len(book_tickers)} pares.")
            except Exception:
                print("   Aviso: nao foi possivel carregar bookTickers. Seguindo sem filtro de spread.")
                book_tickers = {}

            candidates = []
            for symbol in swap_symbols:
                ticker = all_tickers.get(symbol)
                if not ticker:
                    continue
                quote_vol = ticker.get('quoteVolume') or 0
                pct = ticker.get('percentage')
                last = ticker.get('last', 0)

                if quote_vol < min_vol:
                    continue
                if pct is None:
                    continue
                if abs(pct) > max_abs_pct:
                    continue

                spread_pct = 0.0
                raw_sym = symbol.replace('/', '').split(':')[0]
                if raw_sym in book_tickers:
                    bt = book_tickers[raw_sym]
                    bid = bt.get('bid', 0)
                    ask = bt.get('ask', 0)
                    if bid > 0 and ask > 0 and last > 0:
                        spread_pct = ((ask - bid) / last) * 100
                        if spread_pct > max_spread:
                            continue

                candidates.append({
                    'symbol': symbol,
                    'quote_volume': quote_vol,
                    'abs_percentage': abs(pct),
                    'spread_pct': spread_pct,
                })

            if not candidates:
                print("Nenhum ativo passou nos filtros (volume minimo, spread maximo, volatilidade).")
                sys.exit()

            print(f"   {len(candidates)} ativos passaram nos filtros (Vol>={min_vol:,} USDT, Spread<={max_spread}%).")

            vols = np.array([c['quote_volume'] for c in candidates], dtype=float)
            vols_norm = (vols - vols.min()) / (vols.max() - vols.min() + 1e-9)

            volats = np.array([c['abs_percentage'] for c in candidates], dtype=float)
            volats_norm = (volats - volats.min()) / (volats.max() - volats.min() + 1e-9)

            spreads = np.array([c['spread_pct'] for c in candidates], dtype=float)
            has_spread_data = spreads.max() > spreads.min()

            w_volat = ms.get('VOLATILITY_WEIGHT', 0.45)
            w_vol = ms.get('VOLUME_WEIGHT', 0.30)
            w_spread = ms.get('SPREAD_WEIGHT', 0.25)

            if has_spread_data:
                spreads_inv = 1.0 - (spreads - spreads.min()) / (spreads.max() - spreads.min() + 1e-9)
            else:
                spreads_inv = np.ones(len(candidates)) * 0.5
                w_vol += w_spread
                w_spread = 0.0
                print("   Sem dados de spread, redistribuindo peso para volume.")

            for i, c in enumerate(candidates):
                c['score'] = (
                    volats_norm[i] * w_volat
                    + vols_norm[i] * w_vol
                    + spreads_inv[i] * w_spread
                )

            candidates.sort(key=lambda x: x['score'], reverse=True)
            top_n = ms['TOP_N']
            top_assets = candidates[:top_n]

            self.monitored_markets = [
                {"symbol": a['symbol'], **self.config['STRATEGY_CONFIG']}
                for a in top_assets
            ]

            self.asset_states = {
                m['symbol']: {
                    'last_known_trend': None,
                    'active_signal': False,
                    'direction': 0,
                    'entry_price': 0.0,
                    'telegram_message_id': None,
                    'dynamic_targets': [],
                    'targets_hit': 0,
                    'price_at_last_target': 0.0,
                }
                for m in self.monitored_markets
            }

            print(f"\nTop {top_n} selecionado(s):")
            for i, c in enumerate(top_assets):
                print(f"  #{i+1} {c['symbol']} | Vol: ${c['quote_volume']:,.0f} | "
                      f"Var24h: {c['abs_percentage']:.2f}% | Spread: {c['spread_pct']:.4f}% | "
                      f"Score: {c['score']:.3f}")

        except Exception as e:
            print(f"Erro ao rankear ativos: {e}")
            traceback.print_exc()
            sys.exit()

    def _calculate_atr_percent(self, data, period=14):
        high_low = data['high'] - data['low']
        high_close = np.abs(data['high'] - data['close'].shift())
        low_close = np.abs(data['low'] - data['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
        close = data['close'].iloc[-1]
        return (atr / close) * 100 if close else 0

    def _calculate_heikin_ashi(self, data):
        ha = pd.DataFrame(index=data.index, columns=['open', 'high', 'low', 'close'])
        ha['close'] = (data['open'] + data['high'] + data['low'] + data['close']) / 4
        for i in range(len(data)):
            if i == 0:
                ha.at[i, 'open'] = (data['open'].iloc[i] + data['close'].iloc[i]) / 2
            else:
                ha.at[i, 'open'] = (ha.at[i - 1, 'open'] + ha.at[i - 1, 'close']) / 2
        ha['high'] = ha[['open', 'close']].join(data['high']).max(axis=1)
        ha['low'] = ha[['open', 'close']].join(data['low']).min(axis=1)
        return ha

    def _add_halftrend(self, data, amplitude):
        ha = self._calculate_heikin_ashi(data)
        ha['sma_high'] = ha['high'].rolling(amplitude).mean()
        ha['sma_low'] = ha['low'].rolling(amplitude).mean()
        ha['max_high'] = ha['high'].rolling(amplitude).max()
        ha['min_low'] = ha['low'].rolling(amplitude).min()
        ha['next_trend'] = 0
        high_max, low_min = 0.0, 0.0
        for i in range(amplitude, len(ha)):
            close, prev_close = ha['close'].iloc[i], ha['close'].iloc[i - 1]
            trend = ha['next_trend'].iloc[i - 1]
            if trend > 0:
                low_min = max(ha['min_low'].iloc[i], low_min)
                if ha['sma_high'].iloc[i] < low_min and close < prev_close:
                    ha.at[i, 'next_trend'], high_max = -1, ha['max_high'].iloc[i]
                else:
                    ha.at[i, 'next_trend'] = 1
            else:
                high_max = min(ha['max_high'].iloc[i], high_max)
                if ha['sma_low'].iloc[i] > high_max and close > prev_close:
                    ha.at[i, 'next_trend'], low_min = 1, ha['min_low'].iloc[i]
                else:
                    ha.at[i, 'next_trend'] = -1
        data['trend'] = ha['next_trend'].shift(1)
        return data

    def _calc_pct_change(self, current, entry):
        return ((current - entry) / entry) * 100 if entry else 0

    def _send_initial(self, symbol, state, price, atr_pct):
        sig = "COMPRA" if state['direction'] == 1 else "VENDA"
        title = self.config['SIGNAL_MESSAGE']['buy_title'] if sig == "COMPRA" else self.config['SIGNAL_MESSAGE']['sell_title']
        footer = self.config['SIGNAL_MESSAGE']['initial_footer'].format(price=price, atr_percent=atr_pct)
        display = symbol.split(':')[0]
        try:
            msg = _run_async(self.bot.send_message(
                self.config['TELEGRAM']['CHAT_ID'],
                f"<b>{title}</b>\n\n<b>Ativo:</b> {display}{footer}",
                parse_mode='HTML',
            ))
            state['telegram_message_id'] = msg.message_id
            print(f"Alerta INICIAL de {sig} para {symbol} enviado!")
        except Exception as e:
            print(f"Erro ao enviar alerta para {symbol}: {e}")

    def _send_update(self, symbol, state, n, mult, price, total_pct):
        text = self.config['SIGNAL_MESSAGE']['update_reply'].format(
            target_number=n, target_multiplier=mult,
            current_price=price, total_percentage=total_pct,
        )
        try:
            _run_async(self.bot.send_message(
                self.config['TELEGRAM']['CHAT_ID'],
                f"<b>{text}</b>",
                parse_mode='HTML',
                reply_to_message_id=state['telegram_message_id'],
            ))
            print(f"    -> Alvo {n} ({mult:.1f}x ATR) para {symbol}!")
        except Exception as e:
            print(f"    -> Erro ao enviar atualizacao para {symbol}: {e}")

    def run(self):
        self._connect()
        self._find_top_ranked_assets()

        print(f"\nBinance Signal Sentry iniciado!")

        try:
            ms = self.config['MARKET_SELECTION']
            ativos = "\n".join([f"- {m['symbol'].split(':')[0]}" for m in self.monitored_markets])
            _run_async(self.bot.send_message(
                self.config['TELEGRAM']['CHAT_ID'],
                f"<b>Binance Signal Sentry Iniciado!</b>\n\n"
                f"<b>Monitorando ({ms['TOP_N']} ativo(s)):</b>\n{ativos}\n\n"
                f"<b>Filtros:</b>\n"
                f"  - Vol min 24h: ${ms.get('MIN_QUOTE_VOLUME_USDT', 500000):,} USDT\n"
                f"  - Spread max: {ms.get('MAX_SPREAD_PCT', 1.0)}%\n"
                f"  - Var max 24h: {ms.get('MAX_ABS_PERCENTAGE', 100)}%\n"
                f"  - Timeframe: {self.config['STRATEGY_CONFIG']['timeframe']}\n"
                f"  - Scoring: Volatilidade {ms.get('VOLATILITY_WEIGHT', 0.45)} | "
                f"Volume {ms.get('VOLUME_WEIGHT', 0.30)} | "
                f"Spread {ms.get('SPREAD_WEIGHT', 0.25)}\n\n"
                f"Aguardando sinais...",
                parse_mode='HTML',
            ))
        except Exception as e:
            print(f"Erro ao enviar msg inicial no Telegram: {e}")

        while True:
            try:
                active_symbols = [s for s, st in self.asset_states.items() if st['active_signal']]
                if active_symbols:
                    current_tickers = self.exchange.fetch_tickers(active_symbols)
                    for symbol, state in self.asset_states.items():
                        if not state['active_signal'] or symbol not in current_tickers:
                            continue
                        price = current_tickers[symbol]['last']
                        pct = self._calc_pct_change(price, state['entry_price'])
                        progressing = ((state['direction'] == 1 and price > state['price_at_last_target'])
                                       or (state['direction'] == -1 and price < state['price_at_last_target']))
                        if (progressing
                                and state['targets_hit'] < len(state['dynamic_targets'])
                                and abs(pct) >= state['dynamic_targets'][state['targets_hit']]):
                            mults = next(m['ATR_Target_Multipliers'] for m in self.monitored_markets if m['symbol'] == symbol)
                            self._send_update(symbol, state, state['targets_hit'] + 1, mults[state['targets_hit']], price, abs(pct))
                            state['targets_hit'] += 1
                            state['price_at_last_target'] = price

                for market in self.monitored_markets:
                    symbol = market['symbol']
                    state = self.asset_states[symbol]
                    data = self.exchange.fetch_ohlcv(symbol, market['timeframe'], limit=self.config['CANDLE_LIMIT'])

                    if not data or len(data) <= 2:
                        continue

                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    if df['close'].iloc[-1] <= 0:
                        continue

                    df = self._add_halftrend(df, amplitude=market['amplitude'])
                    last_trend = df.iloc[-2]['trend']
                    prev_trend = state['last_known_trend']
                    trend_label = 'ALTA' if last_trend == 1 else 'BAIXA' if last_trend == -1 else 'INDEFINIDA'
                    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {symbol} ({market['timeframe']}) | Tendencia: {trend_label}")

                    if prev_trend is None:
                        state['last_known_trend'] = last_trend
                        continue

                    if not pd.isna(last_trend) and last_trend != prev_trend:
                        state['last_known_trend'] = last_trend

                        allowed = True
                        filt = self.config.get('FILTER_CONFIG', {})
                        if filt.get('enable', False):
                            try:
                                htf_data = self.exchange.fetch_ohlcv(symbol, filt['timeframe'], limit=self.config['CANDLE_LIMIT'])
                                if htf_data and len(htf_data) > filt['amplitude']:
                                    htf_df = pd.DataFrame(htf_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                                    htf_df = self._add_halftrend(htf_df, amplitude=filt['amplitude'])
                                    htf_trend = htf_df.iloc[-2]['trend']
                                    if last_trend == 1 and htf_trend != 1:
                                        allowed = False
                                        print(f"    -> COMPRA BLOQUEADA - HTF ({filt['timeframe']}) nao confirma ALTA.")
                                    elif last_trend == -1 and htf_trend != -1:
                                        allowed = False
                                        print(f"    -> VENDA BLOQUEADA - HTF ({filt['timeframe']}) nao confirma BAIXA.")
                            except Exception as e:
                                print(f"    -> Erro no filtro HTF para {symbol}: {e}")
                                allowed = False

                        if allowed:
                            action = "REVERSAO" if state['active_signal'] else "NOVO SINAL"
                            print(f"    -> {action} para {symbol}!")
                            atr_pct = self._calculate_atr_percent(df)
                            mults = market['ATR_Target_Multipliers']
                            state.update({
                                'active_signal': True,
                                'direction': int(last_trend),
                                'entry_price': df.iloc[-2]['close'],
                                'targets_hit': 0,
                                'dynamic_targets': [m * atr_pct for m in mults],
                                'price_at_last_target': df.iloc[-2]['close'],
                            })
                            self._send_initial(symbol, state, state['entry_price'], atr_pct)
                        else:
                            state['active_signal'] = False

                print(f"\n    -> Ciclo completo. Aguardando {self.config['LOOP_INTERVAL_SECONDS']}s...\n")
                time.sleep(self.config['LOOP_INTERVAL_SECONDS'])

            except KeyboardInterrupt:
                print("\nBot interrompido.")
                break
            except Exception as e:
                print(f"Erro no loop: {e}")
                traceback.print_exc()
                time.sleep(60)


def main():
    try:
        sentry = SignalSentryBinance(CONFIG)
        sentry.run()
    except SystemExit:
        pass
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERRO FATAL: {e}")
        traceback.print_exc()
        print(f"{'='*60}")
    finally:
        try:
            input("\nPressione Enter para sair...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == '__main__':
    main()
