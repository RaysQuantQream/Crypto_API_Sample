from operator import methodcaller
from realtrade.all_common.gateway.private_enum import *
import pandas
import time
import datetime
from realtrade.all_common.util.utility import round_to, load_json_info, round_to_decimal, NoIndent, MyEncoder


# 账户TEST:--------------------------------------------------------------------------------------------------------------------------------------------------------------
exchange_name = 'binance'
market_type = 'spot'
# market_type = 'future_u'
# market_type = 'future_coin'

symbol = 'NEAR-USDT'
# symbol = 'ADA-USDT_PERP'
# symbol = 'ETH-USD_PERP'
position_side = PositionSide.LONG

quote_quantity = 15
test_list = ['get_kline', 'get_latest_price', 'get_24h_ticker', 'get_order_book', 'get_account_info', 'get_balance_info', 'get_position_info', 'place_order', 'place_batch_order']
# test_list = ['get_latest_price', 'place_order']

# 账户：-----------------------------------------------------------------------------------------------------------------------------------------------------------------
key = ""
secret = ''
special_key = None
# proxy_host = '192.168.1.31'
# proxy_port = 7078
proxy_host = '192.168.1.4'
proxy_port = 4780
logic_http = getattr(__import__(f"realtrade.all_common.gateway.{exchange_name}_http", fromlist=(f"gateway.{exchange_name}_http",)), f"{exchange_name}_{market_type}_http")
http_client = logic_http(key=key, secret=secret, special_key=special_key, proxy_host=proxy_host, proxy_port=proxy_port)
exchangeinfo = load_json_info(f"D:/quant/realtrade/all_config_info/exchange_info/exchange_info_{exchange_name}")[f'{exchange_name}_{market_type}']


def split_name(name):
    base_asset = name.split('-')[0]
    asset_type = None
    if '_' in name:
        quote_asset = name.split('-')[1].split('_')[0]
        asset_type = name.split('_')[1]
    else:
        quote_asset = name.split('-')[1]
    if asset_type:
        return base_asset, quote_asset, asset_type
    else:
        return base_asset, quote_asset


def get_exchange_format(exchange_name, market_type):
    path = f"D:/quant/realtrade/all_config_info/exchange_info/exchange_info_{exchange_name}"
    format_text = load_json_info(path)[f"{exchange_name}_{market_type}"]["format"]
    return format_text


def make_trade_name(format_rule, elements):
    if len(elements) == 2:
        trade_name = format_rule.format(elements[0], elements[1])
    else:
        trade_name = format_rule.format(elements[0], elements[1], elements[2])
        if 'SWAP' in trade_name:
            if not elements[2] == 'PERP':
                trade_name.replace('SWAP', elements[2])
    return trade_name


elements = split_name(name=symbol)
format_rule = get_exchange_format(exchange_name=exchange_name, market_type=market_type)
trade_name = make_trade_name(format_rule=format_rule, elements=elements)
qty_precision = exchangeinfo[trade_name]['qty_precision']

# 判断类型
if market_type == 'spot':
    # print(dir(http_client))
    for func in dir(http_client):
        if func in test_list:
            if func == 'get_kline':
                run = methodcaller(func, symbol=trade_name, interval=Interval.HOUR_1)(http_client)
                # print(run)
                if isinstance(run['data'], pandas.DataFrame):
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_latest_price':
                run = methodcaller(func, symbol=trade_name)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    price = run['data'][trade_name]
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_24h_ticker':
                run = methodcaller(func, symbol=trade_name)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_order_book':
                run = methodcaller(func, symbol=trade_name)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    if len(run['data']['datetime']) == 26:
                        print(f'{func}测试成功')
                    else:
                        # print(run)
                        print(f'{func}测试失败')
                        break
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_account_info':
                run = methodcaller(func)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_position_info':
                run = methodcaller(func)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_balance_info':
                run = methodcaller(func)(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'place_order':
                run = methodcaller('get_latest_price', symbol=trade_name)(http_client)
                price = run['data'][trade_name]
                run = methodcaller(func, symbol=trade_name, side=OrderSide.BUY, order_type=OrderType.LIMIT,
                                   quantity=round_to(quote_quantity / (price * 0.8), qty_precision), price=round_to(price * 0.8, qty_precision))(http_client)
                # print(run)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                    time.sleep(1)
                    gto = methodcaller('get_order', order_id=run['data']['order_id'], symbol=trade_name)(http_client)

                    if isinstance(gto, dict):
                        print(f'get_order测试成功')

                    else:
                        # print(run)
                        print(f'get_order测试失败')
                        break

                    gtaoo = methodcaller('get_all_open_order', symbol=trade_name)(http_client)
                    if isinstance(gtaoo['data'], list):
                        print(f'get_all_open_order测试成功')

                    else:
                        # print(run)
                        print(f'get_all_open_order测试失败')
                        break

                    cancel = methodcaller('cancel_order', order_id=run['data']['order_id'], symbol=trade_name)(http_client)
                    if not cancel['success']:
                        print(cancel)
                        print(f'取消订单测试失败')
                        break

                    else:
                        run = methodcaller(func, symbol=trade_name, side=OrderSide.BUY, order_type=OrderType.MARKET, quote_quantity=10, price=price)(http_client)
                        if isinstance(run['data'], dict):
                            print(f'{func}测试成功')
                            time.sleep(1)
                            run = methodcaller(func, symbol=trade_name, side=OrderSide.SELL, order_type=OrderType.MARKET, quote_quantity=10, price=price)(http_client)
                        else:
                            # print(run)
                            print(f'市价下单测试失败')
                            break
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'place_batch_order':
                run = methodcaller('get_latest_price', symbol=trade_name)(http_client)
                price = run['data'][trade_name]
                order_list = [{'symbol': trade_name, 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': round_to(price * 0.8, qty_precision), 'quantity': round_to(quote_quantity / (price * 0.8), qty_precision), 'quote_quantity': None}]
                run = methodcaller(func, order_list=order_list)(http_client)
                # print(run)
                if isinstance(run['data'], list):
                    if len(run['data']) > 0:
                        print(f'{func}测试成功')
                        csa = methodcaller('cancel_all_order', symbol=trade_name)(http_client)
                        if csa['success']:
                            print(f'cancel_all_order测试成功')
                        else:
                            print(csa)
                            print(f'取消全部挂测试失败')
                            break
                else:
                    # print(run)
                    print(f'{func}测试失败')
                    break


if market_type == 'future_u' or market_type == 'future_coin':
    for func in dir(http_client):
        if func in test_list:
            if func == 'get_kline':
                run = methodcaller(func, symbol=trade_name, interval=Interval.HOUR_1)(http_client)
                if isinstance(run['data'], pandas.DataFrame):
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_latest_price':
                run = methodcaller(func, symbol=trade_name)(http_client)
                if isinstance(run['data'], dict):
                    price = run['data'][trade_name]
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_24h_ticker':
                run = methodcaller(func, symbol=trade_name)(http_client)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_order_book':
                run = methodcaller(func, symbol=trade_name)(http_client)
                if isinstance(run['data'], dict):
                    if len(run['data']['datetime']) == 26:
                        print(f'{func}测试成功')
                    else:
                        print(run)
                        print(f'{func}测试失败')
                        break
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_account_info':
                run = methodcaller(func)(http_client)
                if run['success']:
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_position_info':
                run = methodcaller(func)(http_client)
                if isinstance(run['data'], list):
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'get_balance_info':
                run = methodcaller(func)(http_client)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'place_order':
                run = methodcaller('get_latest_price', symbol=trade_name)(http_client)
                price = run['data'][trade_name]
                run = methodcaller(func, symbol=trade_name, side=OrderSide.BUY, order_type=OrderType.LIMIT,
                                   quantity=round_to(quote_quantity / (price * 0.8), qty_precision),
                                   price=round_to(price * 0.8, qty_precision), position_side=position_side)(http_client)
                if isinstance(run['data'], dict):
                    print(f'{func}测试成功')
                    time.sleep(1)
                    gto = methodcaller('get_order', order_id=run['data']['order_id'], symbol=trade_name)(http_client)

                    if isinstance(gto, dict):
                        print(f'get_order测试成功')

                    else:
                        print(run)
                        print(f'get_order测试失败')
                        break

                    gtaoo = methodcaller('get_all_open_order', symbol=trade_name)(http_client)
                    if isinstance(gtaoo, list):
                        print(f'get_all_open_order测试成功')

                    else:
                        print(run)
                        print(f'get_all_open_order测试失败')
                        break

                    cancel = methodcaller('cancel_order', order_id=run['data']['order_id'], symbol=trade_name)(http_client)
                    if not cancel['success']:
                        print(cancel)
                        print(f'取消订单测试失败')
                        break

                    else:
                        run = methodcaller(func, symbol=trade_name, side=OrderSide.BUY, order_type=OrderType.MARKET, quote_quantity=10, price=price, position_side=position_side)(http_client)
                        if isinstance(run['data'], dict):
                            print(f'{func}测试成功')
                            time.sleep(1)
                            run = methodcaller(func, symbol=trade_name, side=OrderSide.SELL, order_type=OrderType.MARKET, quote_quantity=10, position_side=position_side, price=price)(http_client)
                        else:
                            print(run)
                            print(f'市价下单测试失败')
                            break
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break

            elif func == 'place_batch_order':
                run = methodcaller('get_latest_price', symbol=trade_name)(http_client)
                price = run['data'][trade_name]
                order_list = [{'symbol': trade_name, 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': round_to(price * 0.8, qty_precision),
                               'quantity': round_to(quote_quantity / (price * 0.8), qty_precision), 'quote_quantity': None, 'position_side': position_side}]
                run = methodcaller(func, order_list=order_list)(http_client)
                if isinstance(run['data'], list):
                    if len(run['data']) > 0:
                        print(f'{func}测试成功')
                        csa = methodcaller('cancel_all_order', symbol=trade_name)(http_client)
                        if csa['success']:
                            print(f'cancel_all_order测试成功')
                        else:
                            print(csa)
                            print(f'取消全部挂测试失败')
                            break
                else:
                    print(run)
                    print(f'{func}测试失败')
                    break
