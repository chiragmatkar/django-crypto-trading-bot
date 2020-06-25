import unittest
from datetime import datetime
from decimal import Decimal, getcontext
from typing import List, Optional

import pytest
import pytz
from ccxt.base.exchange import Exchange

from django_crypto_trading_bot.trading_bot.api.client import get_client
from django_crypto_trading_bot.trading_bot.exceptions import PriceToHigh, PriceToLow
from django_crypto_trading_bot.trading_bot.models import (
    OHLCV,
    Account,
    Exchanges,
    Market,
    Order,
    Timeframes,
)

from .factories import (
    AccountFactory,
    BuyOrderFactory,
    MarketFactory,
    SellOrderFactory,
    TradeFactory,
    UserFactory,
)


@pytest.mark.django_db()
class Account(unittest.TestCase):

    def test_get_account_client(self):
        account: Account = AccountFactory()
        client: Exchange = account.get_account_client()

        balance: dict = client.fetch_balance()
        assert isinstance(balance, dict)

@pytest.mark.django_db()
class Market(unittest.TestCase):

    def test_symbol(self):
        # check if symbol create the right symbol
        market: Market = MarketFactory()
        assert market.symbol == "TRX/BNB"

        # check if this symbol works on binance
        account: Account = AccountFactory()
        client: Exchange = account.get_account_client()
        client.load_markets()

        market_exchange = client.market(market.symbol)
        assert market.symbol == market_exchange["symbol"]

    def test_get_min_max_order_amount(self):
        market: Market = MarketFactory()
        getcontext().prec = market.precision_amount

        # test minimum
        assert "{:.3f}".format(market.get_min_max_order_amount(market.limits_amount_min / 2)) == "{:.3f}".format(0)
        # test maximum
        assert "{:.3f}".format(market.get_min_max_order_amount(market.limits_amount_max * 2)) == "{:.3f}".format(market.limits_amount_max)
        # test valid amount
        assert "{:.3f}".format(market.get_min_max_order_amount(Decimal(10.3))) == "{:.3f}".format(10.3)
        # test precision_amount 0
        market.precision_amount = 0
        assert "{:.3f}".format(market.get_min_max_order_amount(Decimal(10.321))) == "{:.3f}".format(10)

@pytest.mark.django_db()
class OHLCV(unittest.TestCase):

    def test_get_OHLCV(self):

        market: Market = MarketFactory()
        timeframe: Timeframes = Timeframes.HOUR_1

        test_candel: List[float] = [
            1504541580000,  # UTC timestamp in milliseconds, integer
            4235.4,  # (O)pen price, float
            4240.6,  # (H)ighest price, float
            4230.0,  # (L)owest price, float
            4230.7,  # (C)losing price, float
            37.72941911,  # (V)olume (in terms of the base currency), float
        ]

        ohlcv: OHLCV = OHLCV.get_OHLCV(
            candle=test_candel, timeframe=timeframe, market=market
        )

        assert ohlcv.market == market
        assert ohlcv.timeframe == timeframe
        assert ohlcv.timestamp == datetime(
            year=2017, month=9, day=4, hour=16, minute=13, tzinfo=pytz.UTC
        )
        assert ohlcv.open_price == Decimal(test_candel[1])
        assert ohlcv.highest_price == Decimal(test_candel[2])
        assert ohlcv.lowest_price == Decimal(test_candel[3])
        assert ohlcv.closing_price == Decimal(test_candel[4])
        assert ohlcv.volume == Decimal(test_candel[5])


    def test_create_OHLCV(self):
        market: Market = MarketFactory()
        timeframe: Timeframes = Timeframes.HOUR_1

        test_candel: List[float] = [
            1504541580000,  # UTC timestamp in milliseconds, integer
            4235.4,  # (O)pen price, float
            4240.6,  # (H)ighest price, float
            4230.0,  # (L)owest price, float
            4230.7,  # (C)losing price, float
            37.72941911,  # (V)olume (in terms of the base currency), float
        ]

        ohlcv: OHLCV = OHLCV.create_OHLCV(
            candle=test_candel, timeframe=timeframe, market=market
        )

        assert isinstance(ohlcv.pk, int)  # check if object was saved to db
        assert ohlcv.market == market
        assert ohlcv.timeframe == timeframe
        assert ohlcv.timestamp == datetime(
            year=2017, month=9, day=4, hour=16, minute=13, tzinfo=pytz.UTC
        )
        assert ohlcv.open_price == Decimal(test_candel[1])
        assert ohlcv.highest_price == Decimal(test_candel[2])
        assert ohlcv.lowest_price == Decimal(test_candel[3])
        assert ohlcv.closing_price == Decimal(test_candel[4])
        assert ohlcv.volume == Decimal(test_candel[5])


    def test_last_candle(self):
        market: Market = MarketFactory()
        timeframe: Timeframes = Timeframes.MINUTE_1

        # test without any candle
        assert OHLCV.last_candle(timeframe=timeframe, market=market) is None

        # test with 1 candles
        OHLCV.create_OHLCV(candle=[0, 0, 0, 0, 0, 0], timeframe=timeframe, market=market)
        last_candle_1: Optional[OHLCV] = OHLCV.last_candle(
            timeframe=timeframe, market=market
        )
        assert last_candle_1 is not None
        assert last_candle_1.timestamp == datetime(
            year=1970, month=1, day=1, tzinfo=pytz.UTC
        )

        # test with 2 candles
        OHLCV.create_OHLCV(
            candle=[1504541580000, 0, 0, 0, 0, 0], timeframe=timeframe, market=market
        )
        last_candle_2: Optional[OHLCV] = OHLCV.last_candle(
            timeframe=timeframe, market=market
        )
        assert last_candle_2 is not None
        assert last_candle_2.timestamp == datetime(
            year=2017, month=9, day=4, hour=16, minute=13, tzinfo=pytz.UTC
        )


    def test_update_new_candles(self):
        market: Market = MarketFactory()

        # update market with timeframe of 1 month
        OHLCV.update_new_candles(timeframe=Timeframes.MONTH_1, market=MarketFactory())
        assert (
            OHLCV.objects.filter(timeframe=Timeframes.MONTH_1, market=market).count() > 20
        )

        # update 550 candles
        exchange: Exchange = get_client(exchange_id=market.exchange)
        exchange_time: int = exchange.milliseconds()
        OHLCV.create_OHLCV(
            candle=[exchange_time - 550 * 1000 * 60, 0, 0, 0, 0, 0],
            timeframe=Timeframes.MINUTE_1,
            market=market,
        )
        OHLCV.update_new_candles(timeframe=Timeframes.MINUTE_1, market=MarketFactory())
        candles_amount: int = OHLCV.objects.filter(
            timeframe=Timeframes.MINUTE_1, market=market
        ).count()
        assert candles_amount >= 550
        assert candles_amount <= 553


    # def test_update_new_candles_all_markets(self):
    #     market: Market = MarketFactory()

    #     # update market with timeframe of 1 month
    #     OHLCV.update_new_candles_all_markets(timeframe=Timeframes.MONTH_1)
    #     assert (
    #         OHLCV.objects.filter(timeframe=Timeframes.MONTH_1, market=market).count()
    #         > 20
    #     )


@pytest.mark.django_db()
class Order(unittest.TestCase):
    def test_get_retrade_amount(self):
        buy_order: Order = BuyOrderFactory()
        sell_order: Order = SellOrderFactory()

        getcontext().prec = buy_order.bot.market.precision_amount

        assert "{:.3f}".format(buy_order.get_retrade_amount(price=buy_order.price + Decimal(1))) == "{:.3f}".format(99.9)
        assert "{:.3f}".format(sell_order.get_retrade_amount(price=sell_order.price - Decimal(1))) == "{:.3f}".format(111.1)

    def test_get_retrade_amount_error(self):
        order: Order = BuyOrderFactory()
        with pytest.raises(PriceToLow):
            order.get_retrade_amount(price=Decimal(0))
        with pytest.raises(PriceToHigh):
            order.get_retrade_amount(price=order.bot.market.limits_price_max +  Decimal(10))
