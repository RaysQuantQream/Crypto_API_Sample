"""
    本文件用于连接币安http REST API
    1. Binance http requests.
"""
import csv
import os
from datetime import datetime
import pandas as pd
import requests
import time
import hmac
import hashlib
from realtrade.all_common.gateway.private_enum import *
from realtrade.all_common.util.utility import round_to, load_json_info, round_to_decimal, NoIndent, MyEncoder
from threading import Thread, Lock
import logging
import json
from urllib.parse import urlencode

pd.set_option("expand_frame_repr", False)
pd.set_option('display.max_rows', None)


# 现货类restapi调用
class binance_spot_http(object):

    def __init__(self, key=None, secret=None, proxy_host=None, proxy_port=None, special_key=None, timeout=20):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.broker_IBid = 'x-' + 'zxmTpaKA'
        self.key = key
        self.secret = secret
        self.host = "https://api.binance.com"
        self.recv_window = 10000  # 毫秒=10秒
        self.timeout = timeout
        self.order_count_lock = Lock()
        self.order_count = 1_000_000
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        # 各函数重试最大次数
        self.retry = 10
        file_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).split('\\')
        file_root = file_root[0] + '\\' + file_root[1]
        self.exchangeinfo = load_json_info(f"{file_root}/realtrade/all_config_info/exchange_info/exchange_info_binance")['binance_spot']

    @property
    def proxies(self):
        if self.proxy_port and self.proxy_host:
            proxy = f"http://{self.proxy_host}:{self.proxy_port}"
            return {"http": proxy, "https": proxy}
        return None

    def build_parameters(self, params: dict):
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{k}={params[k]}" for k in params.keys()])

    def make_listen_key(self, need_change_result=True):
        path = '/api/v3/userDataStream'
        re = self.request(RequestMethod.POST, path=path)
        return re

    def _sign(self, params):
        requery_string = self.build_parameters(params)
        hexdigest = hmac.new(self.secret.encode('utf-8'), requery_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return requery_string + '&signature=' + str(hexdigest)

    # 对API参数进行排列加工，返回一串参数的文字
    def request(self, req_method: RequestMethod, path: str, params_dict=None, verify=False):
        url = self.host + path
        if verify:
            query_str = self._sign(params_dict)
            url += '?' + query_str
        elif params_dict:
            url += '?' + self.build_parameters(params_dict)
        # 每次请求固定传入headers
        headers = {"X-MBX-APIKEY": self.key}
        # 自动调取GET方法的值：'GET'

        return requests.request(req_method.value, url=url, headers=headers, timeout=self.timeout, proxies=self.proxies).json()

    # =========================================公共信息查询区=============================================
    # 获取服务器时间
    def server_time(self):
        path = '/api/v3/time'
        return self.request(req_method=RequestMethod.GET, path=path)

    # 获取交易币对信息
    def get_exchange_info(self, symbol_list=None, need_change_result=False):
        # 获取交易所规则和交易对的信息
        path = '/api/v3/exchangeInfo'
        re = self.request(req_method=RequestMethod.GET, path=path)
        if need_change_result:
            if symbol_list:
                data = re['symbols']
                info_dic = {}
                for d in data:
                    if d['symbol'] in symbol_list:
                        dic = {
                            "min_vol": float(d['filters'][2]['minQty']),
                            "qty_precision": float(d['filters'][2]['stepSize']),
                            "min_notional": 0.01,
                            "max_notional": 1000000,
                            "price_precision": float(d['filters'][0]['tickSize'])
                        }

                        info_dic[d['symbol']] = dic
                return info_dic
            else:
                print('请输入品种列表')
                return
        else:
            return re

    # 获取K线信息
    def get_kline(self, symbol, interval: Interval, start_time=None, end_time=None, limit=1000, need_change_result=True):
        # API地址
        path = "/api/v3/klines"
        # 生成参数列表
        query_dict = {"symbol": symbol, "limit": int(limit), "interval": interval.value}
        # 若传入开始和结束时间，则自动加入参数列表
        if start_time:
            start_time = start_time if len(str(start_time)) == 13 else str(int(start_time) * 1000)
            query_dict['startTime'] = start_time
        if end_time:
            end_time = end_time if len(str(end_time)) == 13 else str(int(end_time) * 1000)
            query_dict['endTime'] = end_time

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            df = pd.DataFrame(re, columns={"datetime": 0, 'open': 1, 'high': 2, 'low': 3, 'close': 4,
                                                           'volume': 5, 'close_time': 6, 'trade_money': 7,
                                                           'trade_count': 8, 'buy_volume': 9, 'sell_volume': 10,
                                                           'other': 11})
                            # 筛选需要用到的数据
                            df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
                            # 将格林威治毫秒时间转换为北京时间
                            df['datetime'] = pd.to_datetime(df['datetime'], unit='ms') + pd.Timedelta(hours=8)
                            df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                            return {'success': True, 'data': df.sort_values(by='datetime', ascending=True),
                                    'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': "尝试超过错误"}

    # 获取最新报价
    def get_latest_price(self, symbol=None, need_change_result=True):
        path = "/api/v3/ticker/price"
        query_dict = None
        if symbol:
            query_dict = {"symbol": symbol}

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            re_dict = {}
                            for coin in re:
                                re_dict[coin['symbol']] = float(coin['price'])
                            return {'success': True, 'data': re_dict, 'message': ''}
                        else:
                            return re
                elif isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            re_dict = {re['symbol']: float(re['price'])}
                            return {'success': True, 'data': re_dict, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取24小时价格变动情况
    def get_24h_ticker(self, symbol, need_change_result=True):
        path = "/api/v3/ticker/24hr"
        query_dict = {'symbol': symbol}

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            data_dict = {symbol: {'volume': float(re['volume']),
                                                  'quotevolume': float(re['quoteVolume']),
                                                  'pricechangepercent': float(re['priceChangePercent']) / 100}}
                            return {'success': True, 'data': data_dict, 'message': ''}
            except:
                continue
        return {'success': False, 'data': '', 'message': '24h价格超过尝试错误'}

    def get_all_24h_ticker(self, symbol=None, need_change_result=True):
        path = "/api/v3/ticker/24hr"
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path)
                # print('原始:\n', re)
                if isinstance(re, list):
                    return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '24h价格超过尝试错误'}

    # 获取盘口信息
    def get_order_book(self, symbol, limit=1000, need_change_result=True):
        # 获取交易盘口深度信息,
        limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits:
            limit = 1000
        orderbook = {}
        path = "/api/v3/depth"
        query_dict = {"symbol": symbol, "limit": int(limit)}

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            orderbook['symbol'] = symbol
                            orderbook['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                            orderbook['asks'] = [[float(i[0]), float(i[1])] for i in re['asks']]
                            orderbook['bids'] = [[float(i[0]), float(i[1])] for i in re['bids']]
                            return {'success': True, 'data': orderbook, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # =========================================特殊功能区=========================================

    def get_client_order_id(self):
        if self.broker_IBid:
            with self.order_count_lock:
                self.order_count += 1
                return self.broker_IBid + "000" + str(self._timestamp()) + str(self.order_count)
        else:
            with self.order_count_lock:
                self.order_count += 1
                return "000" + str(self._timestamp()) + str(self.order_count)

    def _new_order_id(self):
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def _timestamp(self):
        return int(time.time() * 1000)

    def order_id(self):
        return str(self._timestamp() + self._new_order_id())

    # =========================================私密信息查询=========================================
    def withdraw_to_wallet(self, coin, quantity, address, chain=None, need_change_result=True):
        path = '/sapi/v1/capital/withdraw/apply'
        params = {"timestamp": self._timestamp(), 'coin': coin, 'amount': float(quantity), 'address': address}
        re = self.request(RequestMethod.POST, path=path, params_dict=params, verify=True)
        # print('原始:\n', re)
        return {'success': True, 'data': re, 'message': ''}

    def get_withdraw_info(self, coin=None, start_time=None, end_time=None, withdraw_id=None, limit=1000, start_page=1, need_change_result=True):
        path = '/sapi/v1/capital/withdraw/history'
        data_sou = {"timestamp": self._timestamp(), "limit": limit}
        if coin:
            data_sou['coin'] = coin.upper()
        if start_time:
            data_sou['startTime'] = int(start_time) if len(str(start_time)) == 13 else int(start_time) * 1000
        if end_time:
            data_sou['endTime'] = int(end_time) if len(str(end_time)) == 13 else int(end_time) * 1000
        if withdraw_id:
            data_sou["withdrawOrderId"] = withdraw_id
        re = self.request(RequestMethod.GET, path=path, params_dict=data_sou, verify=True)
        # print('原始:\n', re)
        return {'success': True, 'data': re, 'message': ''}

    # 获取账户信息
    def get_account_info(self, need_change_result=True):
        path = "/api/v3/account"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        data_dict = {}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re['balances'], list):
                    if len(re['balances']) > 0:
                        if need_change_result:
                            balance_list = re['balances']
                            for num in range(len(balance_list)):
                                if float(balance_list[num]['free']) > 0 or float(balance_list[num]['locked']) > 0:
                                    symbol = balance_list[num]['asset']
                                    data_dict[symbol] = {'free': float(balance_list[num]['free']),
                                                         'locked': float(balance_list[num]['locked'])}
                            return {'success': True, 'data': data_dict, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取持仓信息
    def get_position_info(self, need_change_result=True):
        path = "/api/v3/account"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        data_dict = {}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re['balances'], list) and len(re['balances']) > 0:
                    if need_change_result:
                        balance_list = re['balances']
                        for num in range(len(balance_list)):
                            if float(balance_list[num]['free']) > 0 or float(balance_list[num]['locked']) > 0:
                                symbol = balance_list[num]['asset']
                                data_dict[symbol] = {'free': float(balance_list[num]['free']),
                                                     'locked': float(balance_list[num]['locked'])}
                        return {'success': True, 'data': data_dict, 'message': ''}
                    else:
                        return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取余额信息
    def get_balance_info(self, need_change_result=True):
        path = "/api/v3/account"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        data_dict = {}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re['balances'], list):
                    if len(re['balances']) > 0:
                        if need_change_result:
                            balance_list = re['balances']
                            for num in range(len(balance_list)):
                                if float(balance_list[num]['free']) > 0 or float(balance_list[num]['locked']) > 0:
                                    symbol = balance_list[num]['asset']
                                    data_dict[symbol] = {'free': float(balance_list[num]['free']),
                                                         'locked': float(balance_list[num]['locked'])}
                            return {'success': True, 'data': data_dict, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取交易历史
    def get_trade_history(self, symbol, limit=1000, from_id=None, start_time=None, end_time=None, need_change_result=True):
        need_break = 0
        timelist = []
        symbollist = []
        fxlist = []
        pricelist = []
        qtylist = []
        quoteqtylist = []
        commissionlist = []
        commission_asset_list = []
        order_id_list = []
        id_list = []
        while True:
            path = '/api/v3/myTrades'
            params = {'symbol': symbol, 'timestamp': self._timestamp(), 'limit': limit}
            if from_id:
                params['fromId'] = int(from_id)
            else:
                need_break = 1
            if start_time:
                start_time = int(start_time) if len(str(start_time)) == 13 else int(int(start_time) * 1000)
                params['startTime'] = start_time
            else:
                need_break = 1
            if end_time:
                end_time = int(end_time) if len(str(end_time)) == 13 else int(int(end_time) * 1000)
                params['endTime'] = end_time
            else:
                need_break = 1
            re = self.request(RequestMethod.GET, path, params, verify=True)
            # print('原始:\n', re)
            for i in re:
                timelist.append(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(str(i['time'])[0: -3]))))
                symbollist.append(i['symbol'])
                fx = 'buy' if i['isBuyer'] == True else 'sell'
                fxlist.append(fx)
                pricelist.append(i['price'])
                qtylist.append(i['qty'])
                quoteqtylist.append(i['quoteQty'])
                commissionlist.append(i['commission'])
                commission_asset_list.append(i['commissionAsset'])
                order_id_list.append(i['orderId'])
                id_list.append(i['id'])
            if need_break == 0:
                break
            if len(re) < limit:
                break
            start_time = int(re[-1]['time'])
            if 'endTime' in params.keys():
                end_time = None
                del params['endTime']
            if 'fromId' in params.keys():
                from_id = None
                del params['fromId']
        dic = {}
        dic['time'] = timelist
        dic['symbol'] = symbollist
        dic['fx'] = fxlist
        dic['price'] = pricelist
        dic['qty'] = qtylist
        dic['quoteqty'] = quoteqtylist
        dic['commission'] = commissionlist
        dic['commissionAsset'] = commission_asset_list
        dic['order_id'] = order_id_list
        dic['id'] = id_list
        df = pd.DataFrame(dic)
        df = df.drop_duplicates(subset=['order_id', 'id'], keep='first')
        if need_change_result:
            return {'success': True, 'data': df, 'message': ''}
        else:
            return df

    # =========================================交易相关=========================================

    # 开仓报单，需要密钥验证
    def place_order(self, symbol: str, side: OrderSide, order_type: OrderType, quantity=None, price=None,
                    quote_quantity=None,
                    time_inforce="GTC", recv_window=5000, client_order_id=None, need_change_result=True):
        # 注明：quantity代表数量，quoteOrderQty带表金额
        path = '/api/v3/order'
        if client_order_id is None:
            client_order_id = self.get_client_order_id()
        params = {
            "symbol": symbol,
            "side": side.value.upper(),
            "type": order_type.value.upper(),
            "recvWindow": recv_window,
            "timestamp": self._timestamp(),
            "newClientOrderId": client_order_id
        }
        # 引入需要用的报单数量，或计价报单数量
        if quantity:
            params['quantity'] = quantity
        elif quote_quantity:
            params['quoteOrderQty'] = quote_quantity
        # 限价单
        if order_type.value.lower() == 'limit':
            params['price'] = price
            params['timeInForce'] = time_inforce

        for i in range(self.retry):
            try:

                re = self.request(RequestMethod.POST, path=path, params_dict=params, verify=True)
                # print('原始:\n', re)
                if 'symbol' in re.keys():
                    if need_change_result:
                        re_dic = {'order_id': re['orderId'],
                                  'side': re['side'].lower(),
                                  'qty': float(re['origQty']),
                                  'price': float(re['price']),
                                  'order_type': re['type'].lower(),
                                  'status': re['status'].lower(),
                                  'real_qty': float(re['executedQty']),
                                  'real_price': float(re['cummulativeQuoteQty']) / float(re['executedQty']) if float(
                                      re['executedQty']) > 0 else None}
                        if re['type'] == 'MARKET':
                            re_dic['price'] = float(re['cummulativeQuoteQty']) / float(re['executedQty']) if float(
                                re['executedQty']) > 0 else None
                        return {'success': True, 'data': re_dic, 'message': ''}
                    else:
                        return re
                else:
                    if str(re['code']) == '-2010' and re['msg'] == 'Account has insufficient balance for requested action.':
                        return {'success': False, 'data': '', 'message': 'not enough balance'}
                    elif str(re['code']) == '-1013':
                        return {'success': False, 'data': '', 'message': 'min notional or qty error'}
                    elif str(re['code']) == '-1111' and re[
                        'msg'] == 'Precision is over the maximum defined for this asset.':
                        return {'success': False, 'data': '', 'message': 'price precision error'}
            except:
                continue

        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 批量下单，传入格式：order_list=[{品种，方向，订单类型，价格，数量，成交额}, ...]，其他不用传
    def place_batch_order(self, order_list, time_inforce="GTC", once_max_order=50, need_change_result=True):
        '''币安现货无批量挂单，采用循环单次报单，需注意：每秒报单数量限制'''
        path = '/api/v3/order'
        symbol = order_list[0]['symbol']
        qty_precision = self.exchangeinfo[symbol]['qty_precision']

        if not isinstance(order_list, list):
            print("\033[0;31;40m批量报单，order_list参数需要是列表，传入错误，请检查\033[0m")
            return

        relist = []
        for order in order_list:
            # 币安限制：每10秒最多50次交易请求
            time.sleep(0.25)
            params = {"symbol": order['symbol'].upper(), "side": order['side'].value.upper(),
                      "timestamp": self._timestamp(), "type": order['order_type'].value.upper()}

            # 处理limit
            if order['order_type'].value.lower() == 'limit':
                params['price'] = order['price']
                params['timeInForce'] = time_inforce
                if order['quantity']:
                    params['quantity'] = float(order['quantity'])
                elif order['quote_quantity']:
                    params['quantity'] = round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision)

            # 处理market
            elif order['order_type'].value.lower() == 'market':
                if order['side'].value.lower() == 'sell':
                    if order['quantity']:
                        params['quantity'] = order['quantity']
                    elif order['quote_quantity']:
                        params['quantity'] = round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision)

            # 逐个报单----------------------------------------------------
            for i in range(self.retry):
                try:
                    re = self.request(RequestMethod.POST, path=path, params_dict=params, verify=True)
                    # print('原始:\n', re)
                    if 'symbol' in re:
                        # 如果需要加工结果，格式：
                        if need_change_result:
                            redic = {'symbol': re['symbol'], 'order_id': re['orderId'], 'price': float(re['price']),
                                     'side': re['side'].lower(),
                                     'qty': float(re['origQty']), 'status': re['status'].lower(),
                                     'order_type': re['type'].lower()}
                            relist.append(redic)
                        break
                    else:
                        if str(re['code']) == '-2010' and re['msg'] == 'Account has insufficient balance for requested action.':
                            print(f'\033[0;31;40mbinance - 报单时币种可用资金不足，结束报单，交易所返回：{re}\033[0m')
                            if need_change_result:
                                return {'success': True, 'data': relist, 'message': 'not enough balance'} if len(
                                    relist) > 0 else {'success': False, 'data': '', 'message': 'not enough balance'}
                            else:
                                return re
                        elif str(re['code']) == '-1013' and re['msg'] == 'Filter failure: LOT_SIZE':
                            if need_change_result:
                                return {'success': True, 'data': relist, 'message': 'min notional or qty error'} if len(
                                    relist) > 0 else {'success': False, 'data': '',
                                                      'message': 'min notional or qty error'}
                            else:
                                return re
                        elif str(re['code']) == '-1111' and re[
                            'msg'] == 'Precision is over the maximum defined for this asset.':
                            if need_change_result:
                                return {'success': True, 'data': relist, 'message': 'price precision error'} if len(
                                    relist) > 0 else {'success': False, 'data': '', 'message': 'price precision error'}
                            else:
                                return re
                except:
                    continue
                if i == self.retry - 1:
                    print(f'报单失败，这单没有报成功：{params}')

        # 全部执行完成，返回一个总表
        if need_change_result:
            return {'success': True, 'data': relist, 'message': ''}
        else:
            return relist

    # 查询订单
    def get_order(self, symbol, order_id=None, need_change_result=True):
        path = "/api/v3/order"
        # 查询持仓订单信息，需要品种和毫秒时间
        query_dict = {"symbol": symbol, "timestamp": self._timestamp()}
        if order_id:
            query_dict["orderId"] = order_id

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict, verify=True)
                # print('原始:\n', re)
                if need_change_result:
                    re_dic = {'order_id': re['orderId'],
                              'symbol': re['symbol'],
                              'price': float(re['price']),
                              'side': re['side'].lower(),
                              'qty': float(re['origQty']),
                              'order_type': re['type'],
                              'status': re['status'].lower(),
                              'real_qty': float(re['executedQty']),
                              'real_price': float(re['cummulativeQuoteQty']) / float(re['executedQty']) if float(
                                  re['executedQty']) > 0 else None}
                    return {'success': True, 'data': re_dic, 'message': ''}
                else:
                    return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 取消订单
    def cancel_order(self, symbol, order_id=None, need_change_result=True):
        path = "/api/v3/order"
        params = {"symbol": symbol, "timestamp": self._timestamp()}
        # 如果有订单号，传入订单号
        if order_id:
            params["orderId"] = int(order_id)

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                # print('原始:\n', re)
                if 'symbol' in re:
                    if need_change_result:
                        return {'success': True, 'data': re, 'message': ''}
                    else:
                        return re
                elif re['code'] == -2011:
                    return {'success': False, 'data': '', 'message': 'order filled'}
            except:
                continue

        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取当前账户在交易所的挂单信息
    def get_all_open_order(self, symbol=None, need_change_result=True):
        path = "/api/v3/openOrders"
        # 获取挂单信息，需要传入时间，时间为格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        if symbol:
            params["symbol"] = symbol

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if type(re) == list and len(re) > 0:
                    if need_change_result:
                        new_re = []
                        for d in re:
                            data_dic = {'order_id': d['orderId'],
                                        'symbol': d['symbol'],
                                        'price': float(d['price']),
                                        'side': d['side'].lower(),
                                        'qty': float(d['origQty']),
                                        'order_type': d['type'].lower(),
                                        'status': d['status'].lower(),
                                        'real_qty': float(d['executedQty']),
                                        'real_price': float(d['cummulativeQuoteQty']) / float(
                                            d['executedQty']) if float(d['executedQty']) > 0 else None}
                            new_re.append(data_dic)
                        return {'success': True, 'data': new_re, 'message': ''}
                    else:
                        return re
                elif type(re) == list and len(re) == 0:
                    if need_change_result:
                        return {'success': True, 'data': re, 'message': ''}
                    else:
                        return re
            except:
                continue

        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 撤销所有挂单
    def cancel_all_order(self, symbol, need_change_result=True):
        path = '/api/v3/openOrders'
        params = {
            "timestamp": self._timestamp(),
            "symbol": symbol
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if need_change_result:
                        return {'success': True, 'data': re, 'message': ''}
                    else:
                        return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}


# 期货U本位
class binance_future_u_http(object):

    def __init__(self, key=None, secret=None, proxy_host=None, proxy_port=None, special_key=None, timeout=20):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.broker_IBid = 'x-' + 'zxmTpaKA'
        self.key = key
        self.secret = secret
        self.host = "https://fapi.binance.com"
        self.recv_window = 10000  # 毫秒=10秒
        self.timeout = timeout
        self.order_count_lock = Lock()
        self.order_count = 2_000_000
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        self.retry = 10
        file_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).split('\\')
        file_root = file_root[0] + '\\' + file_root[1]
        self.exchangeinfo = load_json_info(f"{file_root}/realtrade/all_config_info/exchange_info/exchange_info_binance")[
            'binance_future_u']


    @property
    def proxies(self):
        if self.proxy_port and self.proxy_host:
            proxy = f"http://{self.proxy_host}:{self.proxy_port}"
            return {"http": proxy, "https": proxy}
        return None

    # 对API参数进行排列加工，返回一串参数的文字
    def build_parameters(self, params: dict):
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{k}={params[k]}" for k in params.keys()])

    def make_listen_key(self, need_change_result=True):
        path = '/fapi/v1/listenKey'
        return self.request(RequestMethod.GET, path)

    # 用于生成签名的函数，传入API订阅的参数即可
    def _sign(self, params):
        requery_string = self.build_parameters(params)
        hexdigest = hmac.new(self.secret.encode('utf-8'), requery_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return requery_string + '&signature=' + str(hexdigest)

    def hashing(self, query_string):
        return hmac.new(self.secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    def batch_url(self, params_dict, path):
        url = self.host + path
        query_str = urlencode(params_dict)
        query_str = query_str.replace("%27", "%22")
        query_string = "{}&timestamp={}".format(query_str, self._timestamp())
        url += "?" + query_string + "&signature=" + self.hashing(query_string)
        return url

    def request(self, req_method: RequestMethod, path: str, params_dict=None, verify=False):
        url = self.host + path
        # 批量报单需要特殊处理
        if path == '/fapi/v1/batchOrders':
            url = self.batch_url(params_dict=params_dict, path=path)
        elif verify:
            query_str = self._sign(params_dict)
            url += '?' + query_str
        elif params_dict:
            url += '?' + self.build_parameters(params_dict)
        # 每次请求固定传入headers
        headers = {"X-MBX-APIKEY": self.key}
        print(url)
        return requests.request(req_method.value, url=url, headers=headers, timeout=self.timeout,
                                proxies=self.proxies).json()

    # =========================================公共信息查询区=============================================

    # 获取服务器时间
    def server_time(self):
        path = '/fapi/v1/time'
        return self.request(req_method=RequestMethod.GET, path=path)

    # 获取交易币对信息
    def get_exchange_info(self, symbol_list=None, need_change_result=False):
        # 获取交易所规则和交易对的信息
        path = '/fapi/v1/exchangeInfo'
        re = self.request(req_method=RequestMethod.GET, path=path)
        # print(re)
        if need_change_result:
            if symbol_list:
                data = re['symbols']
                info_dic = {}
                for d in data:
                    if d['symbol'] in symbol_list:
                        dic = {
                            "min_vol": float(d['filters'][2]['minQty']),
                            "qty_precision": float(d['filters'][2]['stepSize']),
                            "min_notional": 0.01,
                            "max_notional": 1000000,
                            "price_precision": float(d['filters'][0]['tickSize']),
                            "contractsize": 1
                        }
                        info_dic[d['symbol']] = dic
                return info_dic
        else:
            return re

    # 获取K线信息
    def get_kline(self, symbol, interval: Interval, start_time=None, end_time=None, limit=1500, need_change_result=True):
        path = "/fapi/v1/klines"

        query_dict = {
            "symbol": symbol,
            "limit": int(limit),
            "interval": interval.value
        }

        # 若传入开始和结束时间，则自动加入参数列表
        if start_time:
            start_time = str(start_time) if len(str(start_time)) == 13 else str(int(start_time) * 1000)
            query_dict['startTime'] = start_time
        if end_time:
            end_time = str(end_time) if len(str(end_time)) == 13 else str(int(end_time) * 1000)
            query_dict['endTime'] = end_time

        # 获取数据，若未获取，自动重试
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            df = pd.DataFrame(re, columns={"datetime": 0, 'open': 1, 'high': 2, 'low': 3, 'close': 4,
                                                           'volume': 5, 'close_time': 6, 'trade_money': 7,
                                                           'trade_count': 8, 'buy_volume': 9, 'sell_volume': 10,
                                                           'other': 11})
                            # 筛选需要用到的数据
                            df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
                            # 将格林威治毫秒时间转换为北京时间
                            df['datetime'] = pd.to_datetime(df['datetime'], unit='ms') + pd.Timedelta(hours=8)
                            df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                            return {'success': True, 'data': df.sort_values(by='datetime', ascending=True),
                                    'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取最新报价
    def get_latest_price(self, symbol=None, need_change_result=True):
        path = "/fapi/v1/ticker/price"
        query_dict = None
        if symbol:
            query_dict = {"symbol": symbol}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始：\n', re)
                re_dic = {}
                if type(re) == list and len(re) > 1:
                    if need_change_result:
                        for sb in re:
                            re_dic[sb['symbol']] = float(sb['price'])
                        return {'success': True, 'data': re_dic, 'message': ''}
                    else:
                        return re
                elif type(re) == dict:
                    return {'success': True, 'data': {re['symbol']: float(re['price'])}, 'message': ''}
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取24小时价格变动情况
    def get_24h_ticker(self, symbol, need_change_result=True):
        path = "/fapi/v1/ticker/24hr"
        query_dict = {"symbol": symbol}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, dict) and len(re) > 1:
                    if need_change_result:
                        re_dic = {'volume': float(re['volume']),
                                  'quotevolume': float(re['quoteVolume']),
                                  'pricechangepercent': float(re['priceChangePercent']) / 100}
                        return {'success': True, 'data': re_dic, 'message': ''}
                    else:
                        return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取盘口信息
    def get_order_book(self, symbol, limit=1000, need_change_result=True):
        # 获取交易盘口深度信息,
        limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits:
            limit = 1000
        orderbook = {}
        path = "/fapi/v1/depth"
        query_dict = {"symbol": symbol, "limit": int(limit)}

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            orderbook['symbol'] = symbol
                            orderbook['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                            orderbook['asks'] = [[float(i[0]), float(i[1])] for i in re['asks']]
                            orderbook['bids'] = [[float(i[0]), float(i[1])] for i in re['bids']]
                            return {'success': True, 'data': orderbook, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # =========================================特殊功能区=========================================

    def get_client_order_id(self):
        if self.broker_IBid:
            with self.order_count_lock:
                self.order_count += 1
                return self.broker_IBid + "000" + str(self._timestamp()) + str(self.order_count)
        else:
            with self.order_count_lock:
                self.order_count += 1
                return "000" + str(self._timestamp()) + str(self.order_count)

    def _new_order_id(self):
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def _timestamp(self):
        return int(time.time() * 1000)

    def order_id(self):
        return str(self._timestamp() + self._new_order_id())

    # =========================================私密信息查询=========================================

    # 获取期货账户信息
    def get_account_info(self, recv_window=5000, need_change_result=True):
        path = '/fapi/v2/account'
        params = {'recvWindow': recv_window, 'timestamp': self._timestamp()}

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取期货持仓信息
    def get_position_info(self, recv_window=5000, need_change_result=True):
        path = "/fapi/v2/account"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        if recv_window:
            params['recvWindow'] = recv_window

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            re_list = []
                            for d in re['positions']:
                                if float(d['positionAmt']) != 0:
                                    if d['positionSide'].lower() == 'both':
                                        if float(d['positionAmt']) > 0:
                                            side = 'buy'
                                        else:
                                            side = 'sell'
                                    elif d['positionSide'].lower() == 'long':
                                        side = 'buy'
                                    else:
                                        side = 'sell'
                                    re_dic = {
                                        'symbol': d['symbol'],
                                        'side': side,
                                        'position_side': d['positionSide'].lower(),
                                        'qty': abs(float(d['positionAmt'])),
                                        'entry_price': float(d['entryPrice']),
                                        'unrealized_profit': float(d['unrealizedProfit'])}
                                    re_list.append(re_dic)
                            return {'success': True, 'data': re_list, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取期货账户余额
    def get_balance_info(self, recv_window=5000, need_change_result=True):
        path = "/fapi/v2/account"
        params = {"timestamp": self._timestamp()}
        if recv_window:
            params['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path=path, params_dict=params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            data_dic = {}
                            for d in re['assets']:
                                if float(d['walletBalance']) != 0:
                                    data_dic[d['asset']] = {'free': float(d['availableBalance']),
                                                            'margin_used': float(d['walletBalance']) - float(
                                                                d['availableBalance']),
                                                            'net_balance': float(d['marginBalance'])}
                            return {'success': True, 'data': data_dic, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取交易历史
    def get_trade_history(self, symbol, limit=1000, from_id=None, start_time=None, end_time=None, recv_window=5000, need_change_result=True):
        need_break = 0
        timelist = []
        symbollist = []
        fxlist = []
        possideList = []
        pricelist = []
        qtylist = []
        quoteqtylist = []
        commissionlist = []
        commission_asset_list = []
        order_id_list = []
        id_list = []
        while True:
            path = '/fapi/v1/userTrades'
            params = {'symbol': symbol, 'timestamp': self._timestamp(), 'recvWindow': recv_window, 'limit': limit}
            if from_id:
                params['fromId'] = int(from_id)
            else:
                need_break = 1
            if start_time:
                start_time = int(start_time) if len(str(start_time)) == 13 else int(int(start_time) * 1000)
                params['startTime'] = start_time
            else:
                need_break = 1
            if end_time:
                end_time = int(end_time) if len(str(end_time)) == 13 else int(int(end_time) * 1000)
                params['endTime'] = end_time
            else:
                need_break = 1
            re = self.request(RequestMethod.GET, path, params, verify=True)
            # print('原始:\n', re)
            for i in re:
                timelist.append(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(str(i['time'])[0: -3]))))
                symbollist.append(i['symbol'])
                fx = i['side'].lower()
                fxlist.append(fx)
                possideList.append(i['positionSide'].lower())
                pricelist.append(i['price'])
                qtylist.append(i['qty'])
                quoteqtylist.append(i['quoteQty'])
                commissionlist.append(i['commission'])
                commission_asset_list.append(i['commissionAsset'])
                order_id_list.append(i['orderId'])
                id_list.append(i['id'])
            if need_break == 0:
                break
            if len(re) < limit:
                break
            start_time = int(re[-1]['time'])
            if 'endTime' in params.keys():
                end_time = None
                del params['endTime']
            if 'fromId' in params.keys():
                from_id = None
                del params['fromId']
        dic = {}
        dic['time'] = timelist
        dic['symbol'] = symbollist
        dic['fx'] = fxlist
        dic['position_side'] = possideList
        dic['price'] = pricelist
        dic['qty'] = qtylist
        dic['quoteqty'] = quoteqtylist
        dic['commission'] = commissionlist
        dic['commissionAsset'] = commission_asset_list
        dic['order_id'] = order_id_list
        dic['id'] = id_list
        df = pd.DataFrame(dic)
        df = df.drop_duplicates(subset=['order_id', 'id'], keep='first')
        if need_change_result:
            return {'success': True, 'data': df, 'message': ''}
        else:
            return df

    # 更改持仓模式，双向（ture）、单向（false）
    def change_position_side(self, dual_side_position: dualSideType, recv_window=5000, need_change_result=True):
        path = '/fapi/v1/positionSide/dual'
        params = {
            'dualSidePosition': dual_side_position.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
                    elif re['code'] == -4059:
                        return {'success': True, 'data': re, 'message': 'no need to change'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 查询持仓模式
    def get_position_side(self, recv_window=5000, need_change_result=True):
        path = '/fapi/v1/positionSide/dual'
        params = {
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if 'dualSidePosition' in re:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 查询持仓风险
    def get_position_risk_info(self, symbol=None, recv_window=5000, need_change_result=True):
        # 期货查询当前用户持仓风险
        path = "/fapi/v2/positionRisk"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        if symbol:
            params['symbol'] = symbol
        if recv_window:
            params['recvWindow'] = recv_window

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 变换逐全仓模式，逐仓（ISOLATED），全仓（CROSSED）
    def change_margin_type(self, symbol, margin_type: marginType, recv_window=5000, need_change_result=True):
        path = '/fapi/v1/marginType'
        params = {
            'symbol': symbol.upper(),
            'marginType': margin_type.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 调整逐仓保证金
    def change_position_margin(self, symbol, quantity, type: positionMarginType, position_side: PositionSide = None,
                               recv_window=5000, need_change_result=True):
        amount = quantity
        path = '/fapi/v1/positionMargin'
        params = {
            'symbol': symbol,
            'amount': amount,
            'type': type.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        if position_side:
            params['positionSide'] = position_side.value
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 调整杠杆
    def change_leverage(self, symbol, leverage, recv_window=5000, need_change_result=True):
        path = '/fapi/v1/leverage'
        params = {
            'symbol': symbol.upper(),
            'leverage': leverage,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if 'symbol' in re:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # =========================================交易相关=========================================

    # 开仓报单
    def place_order(self, symbol: str, side: OrderSide, order_type: OrderType, position_side: PositionSide = None,
                    quantity=None, price=None,
                    quote_quantity=None, time_inforce="GTC", recv_window=5000, client_order_id=None,
                    need_change_result=True):
        # 注明：quantity代表数量，quoteOrderQty带表金额
        path = '/fapi/v1/order'
        if client_order_id is None:
            client_order_id = self.get_client_order_id()

        params = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "recvWindow": recv_window,
            "timestamp": self._timestamp(),
            "newClientOrderId": client_order_id
        }
        # 引入需要用的报单数量，或计价报单数量
        if quantity:
            params['quantity'] = quantity
        elif quote_quantity:
            params['quoteOrderQty'] = quote_quantity
        if position_side:
            params['positionSide'] = position_side.value
        # 限价单
        if order_type.value.lower() == 'limit':
            params['price'] = price
            params['timeInForce'] = time_inforce

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path=path, params_dict=params, verify=True)
                # print('原始:\n', re)
                if 'symbol' in re.keys():
                    if need_change_result:
                        re1 = self.get_order(symbol=symbol, order_id=re['orderId'])
                        return re1
                    else:
                        return re
                else:
                    if str(re['code']) == '-2019' and re['msg'] == 'Margin is insufficient.':
                        return {'success': False, 'data': '', 'message': 'not enough balance'}
                    elif str(re['code']) == '-4164':
                        return {'success': False, 'data': '', 'message': 'min notional or qty error'}
                    elif str(re['code']) == '-1111' and re[
                        'msg'] == 'Precision is over the maximum defined for this asset.':
                        return {'success': False, 'data': '', 'message': 'price precision error'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    def get_order(self, symbol, order_id=None, recv_window=5000, need_change_result=True):
        path = "/fapi/v1/order"
        # 查询持仓订单信息，需要品种和毫秒时间
        query_dict = {"symbol": symbol, "timestamp": self._timestamp()}
        if order_id:
            query_dict["orderId"] = order_id
        if recv_window:
            query_dict['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            re_dic = {'symbol': re['symbol'],
                                      'order_id': re['orderId'],
                                      'price': float(re['price']) if float(re['price']) != 0 else float(re['avgPrice']),
                                      'side': re['side'].lower(),
                                      'positionside': re['positionSide'].lower(),
                                      'qty': float(re['origQty']),
                                      'order_type': re['origType'].lower(),
                                      'status': re['status'].lower(),
                                      'real_qty': float(re['executedQty']),
                                      'real_price': float(re['avgPrice']) if float(re['avgPrice']) != 0 else None
                                      }
                            return {'success': True, 'data': re_dic, 'message': ''}
                else:
                    return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 批量下单
    def place_batch_order(self, order_list, time_inforce="GTC", once_max_order=5, recv_window=5000,
                          need_change_result=True):
        path = '/fapi/v1/batchOrders'
        symbol = order_list[0]['symbol']
        qty_precision = self.exchangeinfo[symbol]['qty_precision']
        if not isinstance(order_list, list):
            print("\033[0;31;40m批量报单，order_list参数需要是列表，传入错误，请检查\033[0m")
            return
        relist = []  # 收集返回结果
        real_list = []  # 收集订单列表数据
        start = 0
        end = once_max_order  # 币安U本位每次下单最多5单
        error = ''  # 收集非余额的错误信息
        for order in order_list:
            params = {"symbol": order['symbol'].upper(),
                      "side": order['side'].value.upper(),
                      "type": order['order_type'].value.upper(),
                      'positionSide': order['position_side'].value.upper()}
            # 处理limit
            if order['order_type'].value.lower() == 'limit':
                params['price'] = str(order['price'])
                params['timeInForce'] = time_inforce
                if order['quantity']:
                    params['quantity'] = str(float(order['quantity']))
                elif order['quote_quantity']:
                    params['quantity'] = str(round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision))
            # 处理market
            elif order['order_type'].value.lower() == 'market':
                if order['side'].value.lower() == 'sell':
                    if order['quantity']:
                        params['quantity'] = str(order['quantity'])
                    elif order['quote_quantity']:
                        params['quantity'] = str(
                            round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision))
            real_list.append(params)
        range_num = (len(real_list) // once_max_order) + 1
        if len(real_list) % once_max_order == 0:
            range_num -= 1
        for num in range(range_num):
            data_list = []
            param = {'timestamp': self._timestamp(),
                     'recvWindow': recv_window}
            if num < len(real_list) // 5:
                for i in range(start, end):
                    data_list.append(real_list[i])
                param['batchOrders'] = data_list
                start += once_max_order
                end += once_max_order
            else:
                for i in real_list[start:]:
                    data_list.append(i)
                param['batchOrders'] = data_list
            for i in range(self.retry):
                try:
                    re = self.request(RequestMethod.POST, path, params_dict=param, verify=True)
                    # print('原始:\n', re)
                    if isinstance(re, list):
                        for d in re:
                            if 'symbol' in d:
                                redic = {'symbol': d['symbol'],
                                         'order_id': d['orderId'],
                                         'price': float(d['price']) if float(d['price']) > 0 else float(d['avgPrice']),
                                         'side': d['side'].lower(),
                                         'position_side': d['positionSide'].lower(),
                                         'qty': float(d['origQty']),
                                         'status': d['status'].lower(),
                                         'order_type': d['type'].lower()}
                                relist.append(redic)
                            elif 'msg' in d:
                                if str(d['code']) == '-2019' and d['msg'] == 'Margin is insufficient.':
                                    print(f'\033[0;31;40mbinance - 报单时币种可用资金不足，结束报单，交易所返回：{re}\033[0m')
                                    return {'success': True, 'data': relist,
                                            'message': error + 'not enough balance'} if len(relist) > 0 else {
                                        'success': False, 'data': '', 'message': error + 'not enough balance'}
                                else:
                                    error += d['msg'] + ' '
                        break
                except:
                    continue
                if i == self.retry - 1:
                    return {'success': False, 'data': '', 'message': '尝试超过错误'}
            # 全部执行完成，返回一个总表
        if need_change_result:
            return {'success': True, 'data': relist, 'message': error}
        else:
            return relist

    # 取消订单，取消挂单，调用delete
    def cancel_order(self, symbol, order_id=None, recv_window=None, need_change_result=True):
        path = "/fapi/v1/order"
        params = {"symbol": symbol, "timestamp": self._timestamp()}
        # 如果有订单号，传入订单号
        if order_id:
            params["orderId"] = order_id
        if recv_window:
            params['recvWindow'] = recv_window

        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                if 'symbol' in re:
                    if need_change_result:
                        return {'success': True, 'data': re, 'message': ''}
                    else:
                        return re
                elif 'code' in re:
                    if re['code'] == -2011:
                        return {'success': False, 'data': '', 'message': 'order filled'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 查询挂单 可以根据传入参数选择查询当前挂单还是全部挂单
    def get_all_open_order(self, symbol=None, recv_window=5000, need_change_result=True):
        # 获取全部挂单 pair和symbol不能一起用
        path = "/fapi/v1/openOrders"
        # 获取挂单信息，需要传入时间，时间为格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp(),
                  "recvWindow": recv_window}
        if symbol:
            params["symbol"] = symbol
        re_list = []
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if need_change_result:
                        for d in re:
                            re_dic = {'order_id': d['orderId'],
                                      'symbol': d['symbol'],
                                      'price': float(d['price']) if float(d['price']) != 0 else float(d['avgPrice']),
                                      'side': d['side'].lower(),
                                      'positionside': d['positionSide'].lower(),
                                      'qty': float(d['origQty']),
                                      'order_type': d['origType'].lower(),
                                      'status': d['status'].lower(),
                                      'real_qty': float(d['executedQty']),
                                      'real_price': float(d['avgPrice']) if float(d['avgPrice']) != 0 else None
                                      }
                            re_list.append(re_dic)
                        return {'success': True, 'data': re_list, 'message': ''}
                    else:
                        return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    def cancel_all_order(self, symbol, recv_window=5000, need_change_result=True):
        path = '/fapi/v1/allOpenOrders'
        params = {
            "timestamp": self._timestamp(),
            "symbol": symbol,
            "recvWindow": recv_window
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                # print('原始\n', re)
                if 'code' in re:
                    if str(re['code']) == "200":
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}


# 期货币本位
class binance_future_coin_http(object):

    def __init__(self, key=None, secret=None, proxy_host=None, proxy_port=None, special_key=None, timeout=20):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.broker_IBid = 'x-' + 'zxmTpaKA'
        # self.broker_IBid = None
        # self.proxies = {"https": "https://10.122.16.171:7078"}
        self.key = key
        self.secret = secret
        self.host = "https://dapi.binance.com"
        self.recv_window = 10000  # 毫秒=10秒
        self.timeout = timeout
        self.order_count_lock = Lock()
        self.order_count = 2_000_000
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        self.retry = 10
        file_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).split('\\')
        file_root = file_root[0] + '\\' + file_root[1]
        self.exchangeinfo = load_json_info(f"{file_root}/realtrade/all_config_info/exchange_info/exchange_info_binance")[
            'binance_future_coin']
        self.side_multiply = {'both': 1, 'long': 1, 'short': -1}

    @property
    def proxies(self):
        if self.proxy_port and self.proxy_host:
            proxy = f"http://{self.proxy_host}:{self.proxy_port}"
            return {"http": proxy, "https": proxy}
        return None

    # 对API参数进行排列加工，返回一串参数的文字
    def build_parameters(self, params: dict):
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{k}={params[k]}" for k in params.keys()])

    # 用于生成签名的函数，传入API订阅的参数即可
    def _sign(self, params):
        # 根据参数字典，生成参数字符串
        requery_string = self.build_parameters(params)
        # 把密钥和参数字符串加密后拼接在字符串中，用于API调用时发送出去
        hexdigest = hmac.new(self.secret.encode('utf-8'), requery_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return requery_string + '&signature=' + str(hexdigest)

    def hashing(self, query_string):
        return hmac.new(
            self.secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def batch_url(self, params_dict, path):
        url = self.host + path
        query_str = urlencode(params_dict)
        query_str = query_str.replace("%27", "%22")
        query_string = "{}&timestamp={}".format(query_str, self._timestamp())
        url += "?" + query_string + "&signature=" + self.hashing(query_string)
        return url

    def request(self, req_method: RequestMethod, path: str, params_dict=None, verify=False):
        url = self.host + path
        if path == '/dapi/v1/batchOrders':
            url = self.batch_url(params_dict=params_dict, path=path)
        elif verify:
            query_str = self._sign(params_dict)
            url += '?' + query_str
        elif params_dict:
            url += '?' + self.build_parameters(params_dict)
        # 每次请求固定传入headers
        headers = {"X-MBX-APIKEY": self.key}
        return requests.request(req_method.value, url=url, headers=headers, timeout=self.timeout,
                                proxies=self.proxies).json()

    # =========================================公共信息查询区=============================================
    # 获取服务器时间
    def server_time(self):
        path = '/dapi/v1/time'
        return self.request(req_method=RequestMethod.GET, path=path)

    # 获取币对信息
    def get_exchange_info(self, symbol_list=None, need_change_result=False):
        # 获取交易所规则和交易对的信息
        path = '/dapi/v1/exchangeInfo'
        re = self.request(req_method=RequestMethod.GET, path=path)

        if need_change_result:
            if symbol_list:
                data = re['symbols']
                info_dic = {}
                for d in data:
                    if d['symbol'] in symbol_list:
                        dic = {
                            "min_vol": float(d['filters'][2]['minQty']),
                            "qty_precision": float(d['filters'][2]['stepSize']),
                            "min_notional": 0.01,
                            "max_notional": 1000000,
                            "price_precision": float(d['filters'][0]['tickSize']),
                            "contractsize": float(d['contractSize'])
                        }
                        info_dic[d['symbol']] = dic
                return info_dic
        else:
            return re

    # 获取K线信息，传入品种信息，周期，默认：无开始和结束的时间自动获取最新+200根K线数据+未获取时自动重试10次
    def get_kline(self, symbol, interval: Interval, start_time=None, end_time=None, limit=300, need_change_result=True):
        # API地址
        path = "/dapi/v1/klines"
        # 生成参数列表
        query_dict = {
            "symbol": symbol,
            "limit": int(limit),
            "interval": interval.value
        }
        # 若传入开始和结束时间，则自动加入参数列表

        if start_time:
            start_time = start_time if len(str(start_time)) == 13 else str(int(start_time) * 1000)
            query_dict['startTime'] = start_time
        if end_time:
            end_time = start_time if len(str(end_time)) == 13 else str(int(end_time) * 1000)
            query_dict['endTime'] = end_time
        # 获取数据，若未获取，自动重试
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            df = pd.DataFrame(re, columns={"datetime": 0, 'open': 1, 'high': 2, 'low': 3, 'close': 4,
                                                           'volume': 5, 'close_time': 6, 'trade_money': 7,
                                                           'trade_count': 8,
                                                           'buy_volume': 9, 'sell_volume': 10, 'other': 11})
                            # 筛选需要用到的数据
                            df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
                            # 将格林威治毫秒时间转换为北京时间
                            df['datetime'] = pd.to_datetime(df['datetime'], unit='ms') + pd.Timedelta(hours=8)
                            df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
                            return {'success': True, 'data': df.sort_values(by='datetime', ascending=True),
                                    'message': ''}
                        else:
                            return re
            except:
                continue
        # print("gate_K线数据获取错误，返回：", re)
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取最新报价
    def get_latest_price(self, symbol=None, need_change_result=True):
        path = "/dapi/v1/ticker/price"
        query_dict = None
        if symbol:
            query_dict = {"symbol": symbol}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始：\n', re)
                re_dic = {}
                if type(re) == list:
                    if len(re) > 0:
                        if need_change_result:
                            for sb in re:
                                re_dic[sb['symbol']] = float(sb['price'])
                            return {'success': True, 'data': re_dic, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取24小时信息
    def get_24h_ticker(self, symbol, need_change_result=True):
        path = "/dapi/v1/ticker/24hr"
        query_dict = {"symbol": symbol}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            re_dic = {'volume': float(re[0]['volume']),
                                      'quotevolume': float(re[0]['baseVolume']),
                                      'pricechangepercent': float(re[0]['priceChangePercent']) / 100}
                            return {'success': True, 'data': re_dic, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取订单簿
    def get_order_book(self, symbol, limit=1000, need_change_result=True):
        # 获取交易盘口深度信息,
        limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits:
            limit = 1000
        orderbook = {}
        path = "/dapi/v1/depth"
        query_dict = {"symbol": symbol, "limit": int(limit)}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            orderbook['symbol'] = symbol
                            orderbook['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                            orderbook['asks'] = [[float(i[0]), float(i[1])] for i in re['asks']]
                            orderbook['bids'] = [[float(i[0]), float(i[1])] for i in re['bids']]
                            return {'success': True, 'data': orderbook, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # =========================================特殊功能区=============================================
    def get_client_order_id(self):
        if self.broker_IBid:
            with self.order_count_lock:
                self.order_count += 1
                return self.broker_IBid + "000" + str(self._timestamp()) + str(self.order_count)
        else:
            with self.order_count_lock:
                self.order_count += 1
                return "000" + str(self._timestamp()) + str(self.order_count)

    def _new_order_id(self):
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    # 用于将时间转换为毫秒
    def _timestamp(self):
        return int(time.time() * 1000)

    def order_id(self):
        return str(self._timestamp() + self._new_order_id())

    def make_listen_key(self, need_change_result=True):
        path = '/dapi/v1/listenKey'
        re = self.request(RequestMethod.GET, path)
        return re

    # =========================================交易相关=============================================
    # 获取期货账户信息
    def get_account_info(self, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/account'
        params = {'recvWindow': recv_window, 'timestamp': self._timestamp()}
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取持仓信息
    def get_position_info(self, recv_window=5000, need_change_result=True):
        path = "/dapi/v1/account"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        if recv_window:
            params['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            re_list = []
                            for d in re['positions']:
                                if float(d['positionAmt']) != 0:
                                    if d['positionSide'].lower() == 'both':
                                        if float(d['positionAmt']) > 0:
                                            side = 'buy'
                                        else:
                                            side = 'sell'
                                    else:
                                        side = 'buy'
                                    re_dic = {
                                        'symbol': d['symbol'],
                                        'side': side,
                                        'position_side': d['positionSide'].lower(),
                                        'qty': abs(float(d['positionAmt'])),
                                        'entry_price': float(d['entryPrice']),
                                        'unrealized_profit': float(d['unrealizedProfit'])}
                                    re_list.append(re_dic)
                            return {'success': True, 'data': re_list, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 期货账户用，查询账户余额
    def get_balance_info(self, recv_window=5000, need_change_result=True):
        path = "/dapi/v1/account"
        params = {"timestamp": self._timestamp()}
        if recv_window:
            params['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path=path, params_dict=params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            data_dic = {}
                            for d in re['assets']:
                                if float(d['walletBalance']) != 0:
                                    data_dic[d['asset']] = {'free': float(d['availableBalance']),
                                                            'margin_used': float(d['walletBalance']) - float(
                                                                d['availableBalance']),
                                                            'net_balance': float(d['marginBalance'])}
                            return {'success': True, 'data': data_dic, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 获取交易历史
    def get_trade_history(self, symbol, limit=1000, from_id=None, start_time=None, end_time=None, recv_window=5000, need_change_result=True):
        need_break = 0
        timelist = []
        symbollist = []
        fxlist = []
        possideList = []
        pricelist = []
        qtylist = []
        quoteqtylist = []
        commissionlist = []
        commission_asset_list = []
        order_id_list = []
        id_list = []
        while True:
            path = '/dapi/v1/userTrades'
            params = {'symbol': symbol, 'timestamp': self._timestamp(), 'recvWindow': recv_window, 'limit': limit}
            if from_id:
                params['fromId'] = int(from_id)
            else:
                need_break = 1
            if start_time:
                start_time = int(start_time) if len(str(start_time)) == 13 else int(int(start_time) * 1000)
                params['startTime'] = start_time
            else:
                need_break = 1
            if end_time:
                end_time = int(end_time) if len(str(end_time)) == 13 else int(int(end_time) * 1000)
                params['endTime'] = end_time
            else:
                need_break = 1
            re = self.request(RequestMethod.GET, path, params, verify=True)
            # print('原始:\n', re)
            for i in re:
                timelist.append(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(str(i['time'])[0: -3]))))
                symbollist.append(i['symbol'])
                fx = i['side'].lower()
                fxlist.append(fx)
                possideList.append(i['positionSide'].lower())
                pricelist.append(i['price'])
                qtylist.append(i['qty'])
                quoteqtylist.append(i['quoteQty'])
                commissionlist.append(i['commission'])
                commission_asset_list.append(i['commissionAsset'])
                order_id_list.append(i['orderId'])
                id_list.append(i['id'])
            if need_break == 0:
                break
            if len(re) < limit:
                break
            start_time = int(re[-1]['time'])
            if 'endTime' in params.keys():
                end_time = None
                del params['endTime']
            if 'fromId' in params.keys():
                from_id = None
                del params['fromId']
        dic = {}
        dic['time'] = timelist
        dic['symbol'] = symbollist
        dic['fx'] = fxlist
        dic['position_side'] = possideList
        dic['price'] = pricelist
        dic['qty'] = qtylist
        dic['quoteqty'] = quoteqtylist
        dic['commission'] = commissionlist
        dic['commissionAsset'] = commission_asset_list
        dic['order_id'] = order_id_list
        dic['id'] = id_list
        df = pd.DataFrame(dic)
        df = df.drop_duplicates(subset=['order_id', 'id'], keep='first')
        if need_change_result:
            return {'success': True, 'data': df, 'message': ''}
        else:
            return df

    # 更改持仓模式，双向（ture）还是单向（false）
    def change_position_side(self, dual_side_position: dualSideType, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/positionSide/dual'
        params = {
            'dualSidePosition': dual_side_position.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
                    elif re['code'] == -4059:
                        return {'success': True, 'data': re, 'message': 'no need to change'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 获取持仓方向
    def get_position_side(self, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/positionSide/dual'
        params = {
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if 'dualSidePosition' in re:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 期货查询当前用户持仓风险
    def get_position_risk_info(self, symbol=None, recv_window=5000, need_change_result=True):
        path = "/dapi/v1/positionRisk"
        # 查询持仓信息需要传入格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp()}
        if symbol:
            params['symbol'] = symbol
        if recv_window:
            params['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if len(re) > 0:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 调整开仓杠杆
    def change_leverage(self, symbol, leverage, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/leverage'
        params = {'symbol': symbol.upper(),
                  'leverage': leverage,
                  'recvWindow': recv_window,
                  'timestamp': self._timestamp()
                  }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if 'symbol' in re:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 变换逐全仓模式，逐仓（ISOLATED），全仓（CROSSED）
    def change_margin_type(self, symbol, margin_type: marginType, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/marginType'
        params = {
            'symbol': symbol.upper(),
            'marginType': margin_type.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 调整逐仓保证金
    def change_position_margin(self, symbol, quantity, type: positionMarginType, position_side: PositionSide = None,
                               recv_window=5000, need_change_result=True):
        amount = quantity
        path = '/dapi/v1/positionMargin'
        params = {
            'symbol': symbol.upper(),
            'amount': amount,
            'type': type.value,
            'recvWindow': recv_window,
            'timestamp': self._timestamp()
        }
        if position_side:
            params['positionSide'] = position_side.value
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path, params, verify=True)
                # print('原始:\n', re)
                if 'code' in re:
                    if re['code'] == 200:
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
                    elif re['code'] == -4051:
                        if need_change_result:
                            return {'success': False, 'data': '', 'message': 'not enough balance'}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}

    # 开仓报单，需要密钥验证 用POST
    def place_order(self, symbol: str, side: OrderSide, order_type: OrderType, position_side: PositionSide = None,
                    quantity=None, price=None, trade_mode=None,
                    quote_quantity=None, time_inforce="GTC", recv_window=5000, client_order_id=None,
                    need_change_result=True):
        # 注明：quantity代表数量，quoteOrderQty带表金额
        path = '/dapi/v1/order'
        if client_order_id is None:
            client_order_id = self.get_client_order_id()
        params = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "recvWindow": recv_window,
            "timestamp": self._timestamp(),
            "newClientOrderId": client_order_id
        }
        # 引入需要用的报单数量，或计价报单数量
        if quantity:
            params['quantity'] = quantity
        elif quote_quantity:
            params['quoteOrderQty'] = quote_quantity
        if position_side:
            params['positionSide'] = position_side.value
        # 限价单
        if order_type.value.lower() == 'limit':
            params['price'] = price
            params['timeInForce'] = time_inforce
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.POST, path=path, params_dict=params, verify=True)
                # print('原始:\n', re)
                if 'symbol' in re.keys():
                    if need_change_result:
                        re1 = self.get_order(symbol=symbol, order_id=re['orderId'])
                        return re1
                    else:
                        return re
                else:
                    if str(re['code']) == '-2019' and re['msg'] == 'Margin is insufficient.':
                        return {'success': False, 'data': '', 'message': 'not enough balance'}
                    elif str(re['code']) == '-4164':
                        return {'success': False, 'data': '', 'message': 'min notional or qty error'}
                    elif str(re['code']) == '-1111' and re[
                        'msg'] == 'Precision is over the maximum defined for this asset.':
                        return {'success': False, 'data': '', 'message': 'price precision error'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 查询订单
    def get_order(self, symbol, order_id=None, recv_window=5000, need_change_result=True):
        path = "/dapi/v1/order"
        # 查询持仓订单信息，需要品种和毫秒时间
        query_dict = {"symbol": symbol, "timestamp": self._timestamp()}
        if order_id:
            query_dict["orderId"] = order_id
        if recv_window:
            query_dict['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, query_dict, verify=True)
                # print('原始:\n', re)
                if isinstance(re, dict):
                    if len(re) > 0:
                        if need_change_result:
                            re_dic = {'symbol': re['symbol'],
                                      'order_id': re['orderId'],
                                      'price': float(re['price']) if float(re['price']) != 0 else float(re['avgPrice']),
                                      'side': re['side'].lower(),
                                      'positionside': re['positionSide'].lower(),
                                      'qty': float(re['origQty']),
                                      'order_type': re['origType'].lower(),
                                      'status': re['status'].lower(),
                                      'real_qty': float(re['executedQty']),
                                      'real_price': float(re['avgPrice']) if float(re['avgPrice']) != 0 else None
                                      }
                            return {'success': True, 'data': re_dic, 'message': ''}
                else:
                    return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 批量下单，batchOrders在这里属性是一个list
    def place_batch_order(self, order_list, time_inforce="GTC", once_max_order=5, recv_window=5000,
                          need_change_result=True):
        path = '/dapi/v1/batchOrders'
        symbol = order_list[0]['symbol']
        qty_precision = self.exchangeinfo[symbol]['qty_precision']
        if not isinstance(order_list, list):
            print("\033[0;31;40m批量报单，order_list参数需要是列表，传入错误，请检查\033[0m")
            return
        relist = []  # 收集返回结果
        real_list = []  # 收集订单列表数据
        start = 0
        end = once_max_order  # 币安U本位每次下单最多5单
        error = ''  # 收集非余额的错误信息
        for order in order_list:
            params = {"symbol": order['symbol'].upper(),
                      "side": order['side'].value.upper(),
                      "type": order['order_type'].value.upper(),
                      'positionSide': order['position_side'].value.upper()}
            # 处理limit
            if order['order_type'].value.lower() == 'limit':
                params['price'] = str(order['price'])
                params['timeInForce'] = time_inforce
                if order['quantity']:
                    params['quantity'] = str(float(order['quantity']))
                elif order['quote_quantity']:
                    params['quantity'] = str(round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision))
            # 处理market
            elif order['order_type'].value.lower() == 'market':
                if order['side'].value.lower() == 'sell':
                    if order['quantity']:
                        params['quantity'] = str(order['quantity'])
                    elif order['quote_quantity']:
                        params['quantity'] = str(
                            round_to_decimal(float(order['quote_quantity']) / order['price'], qty_precision))
            real_list.append(params)
        range_num = (len(real_list) // once_max_order) + 1
        if len(real_list) % once_max_order == 0:
            range_num -= 1
        for num in range(range_num):
            data_list = []
            param = {'timestamp': self._timestamp(),
                     'recvWindow': recv_window}
            if num < len(real_list) // 5:
                for i in range(start, end):
                    data_list.append(real_list[i])
                param['batchOrders'] = data_list
                start += once_max_order
                end += once_max_order
            else:
                for i in real_list[start:]:
                    data_list.append(i)
                param['batchOrders'] = data_list
            for i in range(self.retry):
                try:
                    re = self.request(RequestMethod.POST, path, params_dict=param, verify=True)
                    # print('原始:\n', re)
                    if isinstance(re, list):
                        for d in re:
                            if 'symbol' in d:
                                redic = {'symbol': d['symbol'],
                                         'order_id': d['orderId'],
                                         'price': float(d['price']) if float(d['price']) > 0 else float(d['avgPrice']),
                                         'side': d['side'].lower(),
                                         'position_side': d['positionSide'].lower(),
                                         'qty': float(d['origQty']),
                                         'status': d['status'].lower(),
                                         'order_type': d['type'].lower()}
                                relist.append(redic)
                            elif 'msg' in d:
                                if str(d['code']) == '-2019' and d['msg'] == 'Margin is insufficient.':
                                    print(f'\033[0;31;40mbinance - 报单时币种可用资金不足，结束报单，交易所返回：{re}\033[0m')
                                    return {'success': True, 'data': relist,
                                            'message': error + 'not enough balance'} if len(relist) > 0 else {
                                        'success': False, 'data': '', 'message': error + 'not enough balance'}
                                else:
                                    error += d['msg'] + ' '
                        break
                except:
                    continue
                if i == self.retry - 1:
                    return {'success': False, 'data': '', 'message': '尝试超过错误'}
            # 全部执行完成，返回一个总表
        if need_change_result:
            return {'success': True, 'data': relist, 'message': error}
        else:
            return relist

    # 取消订单，取消挂单，调用delete
    def cancel_order(self, symbol, order_id=None, recv_window=None, need_change_result=True):
        path = "/dapi/v1/order"
        params = {"symbol": symbol, "timestamp": self._timestamp()}
        # 如果有订单号，传入订单号
        if order_id:
            params["orderId"] = order_id
        if recv_window:
            params['recvWindow'] = recv_window
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                if 'symbol' in re:
                    if need_change_result:
                        return {'success': True, 'data': re, 'message': ''}
                    else:
                        return re
                elif 'code' in re:
                    if re['code'] == -2011:
                        return {'success': False, 'data': '', 'message': 'order filled'}
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 查询挂单 可以根据传入参数选择查询当前挂单还是全部挂单
    def get_all_open_order(self, symbol=None, recv_window=5000, need_change_result=True):
        # 获取全部挂单 pair和symbol不能一起用
        path = "/dapi/v1/openOrders"
        # 获取挂单信息，需要传入时间，时间为格林威治毫秒时间*1000
        params = {"timestamp": self._timestamp(),
                  "recvWindow": recv_window}
        if symbol:
            params["symbol"] = symbol
        re_list = []
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.GET, path, params, verify=True)
                # print('原始:\n', re)
                if isinstance(re, list):
                    if need_change_result:
                        for d in re:
                            re_dic = {
                                'order_id': d['orderId'],
                                'symbol': d['symbol'],
                                'price': float(d['price']) if float(d['price']) > 0 else float(d['avgPrice']),
                                'side': d['side'].lower(),
                                'positionside': d['positionSide'].lower(),
                                'qty': float(d['origQty']),
                                'order_type': d['origType'].lower(),
                                'status': d['status'].lower(),
                                'real_qty': float(d['executedQty']),
                                'real_price': float(d['avgPrice']) if float(d['avgPrice']) != 0 else None
                            }
                            re_list.append(re_dic)
                        return {'success': True, 'data': re_list, 'message': ''}
                    else:
                        return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '尝试多次均失败'}

    # 取消全部挂单
    def cancel_all_order(self, symbol, recv_window=5000, need_change_result=True):
        path = '/dapi/v1/allOpenOrders'
        params = {
            "timestamp": self._timestamp(),
            "symbol": symbol,
            "recvWindow": recv_window
        }
        for i in range(self.retry):
            try:
                re = self.request(RequestMethod.DELETE, path, params, verify=True)
                # print('原始\n', re)
                if 'code' in re:
                    if str(re['code']) == "200":
                        if need_change_result:
                            return {'success': True, 'data': re, 'message': ''}
                        else:
                            return re
            except:
                continue
        return {'success': False, 'data': '', 'message': '超过尝试错误'}


if __name__ == '__main__':
    # 设置APIkey

    # 账户TEST:--------------------------------------
    name = 'test'
    # key = ''
    key = ""
    secret = ''
    # proxy_host = '192.168.1.31'
    # proxy_port = 7078
    proxy_host = '192.168.1.4'
    proxy_port = 4780
    # 测试用：
    # 现货--------------------------------------------------------------------------------------------------------------
    binance = binance_future_u_http(key=key, secret=secret, proxy_host=proxy_host, proxy_port=proxy_port)
    # data = binance.exchangeInfo()
    # print(data)
    #
    data = binance.get_order_book(symbol='BTCUSDT')
    print(data)
    # data = binance.get_trade_history(symbol='BTCUSDT')
    # print(data)
    # exit()
    # binance = binance_spot_http(key=key, secret=secret, proxy_host=proxy_host, proxy_port=proxy_port)
    # data = binance.get_account_info()
    # print(data)
    # data = binance.cancel_order(order_id='1174946121', symbol='NEARUSDT')
    # print(data)
    # data = binance.get_all_open_order()
    # print(data)
    exit()
    # data = binance.get_kline(symbol='TUSDT', interval=Interval.MINUTE_5, start_time=1645891200 ,need_change_result=True)
    # print(data)
    # list_temp = []
    # data = binance.exchangeInfo()
    # print(data['symbols'][0])
    # print(type(data['symbols']))
    # for d in data['symbols']:
    #     if d['quoteAsset'] == 'USDT':
    #         if d['isSpotTradingAllowed']:
    #             list_temp.append(d['symbol'])
    # print(list_temp)
    # exit()
    # binance = binance_future_u_http(key=key, secret=secret, proxy_host=proxy_host, proxy_port=proxy_port)
    # re = binance.get_position_info()
    # print('下单前\n', re)
    # data = binance.place_order(symbol='LINAUSDT', quantity=300, price=0.0231, quote_quantity=None, side=OrderSide.SELL,
    #                            position_side=PositionSide.LONG, order_type=OrderType.MARKET)
    # print('加工:\n', data)
    # re = binance.get_position_info()
    # print('下单后\n', re)
    # re = binance.get_balance_info()
    # re = binance.get_all_open_order()
    # print('下单前\n', re)
    # re = binance.make_listen_key()
    # data = binance.place_order(symbol='ETHUSD_PERP', side=OrderSide.BUY, quantity=1, price=2100, order_type=OrderType.LIMIT, position_side=PositionSide.LONG)
    # print(data)
    # data = binance.get_position_side()
    # print(data)
    # data = binance.get_all_open_order(symbol='ADAUSDT')
    # data = binance.cancel_all_order(symbol='ETHUSD_PERP')
    # print('加工\n', data)

    # re = binance.get_balance_info()
    # re = binance.get_all_open_order()
    # print('下单后\n', re)
    # po = binance.get_position_info()
    # print(po)
    # for i in data:
    #     r = binance.get_order(symbol='ADAUSDT', order_id=i['id'])
    #     print(r)
    #     relist.append(r['data'])
    exit()
    # id: 37140982372; 37147253495; 37147253495; 37149340347
    # data = binance.get_order_book(symbol='ETHUSDT')
    # data = binance.exchangeInfo()
    # print('报单前:\n', data)
    # data = binance.get_all_open_order()
    # data = binance.place_order(symbol='ADAUSDT', side=OrderSide.SELL, order_type=OrderType.LIMIT, price=4000, quantity=0.1)
    # print('加工:\n', data)
    # data = binance.cancel_order(order_id='7294892128', symbol='ETHUSDT')
    # data = binance.get_balance_info()
    # print('报单前:\n', data)
    # data = binance.place_order(symbol='ADAUSDT', side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=8, price=2)
    # print('加工:\n', data)
    # data = binance.get_balance_info()
    # print('报单后:\n', data)
    # data = binance.cancel_order(symbol='ADAUSDT', order_id='2788478533')
    # print('加工:\n', data)

    # exit() data = binance.get_balance_info() print('报单后:\n', data) 获取交易所全部币种信息-------------------- ['timezone',
    # 'serverTime', 'rateLimits', 'exchangeFilters', 'symbols'] '2747610948' data = binance.cancel_order(
    # symbol='ADAUSDT', order_id='2747610948') data = binance.get_order(symbol='ADAUSDT', order_id='2747610948') data
    # = binance.get_all_open_order() data = binance.get_order(symbol='ADAUSDT', order_id='2788501084') print('加工:\n',
    # data) for i in data['data']: re = binance.cancel_order(symbol=i['symbol'], order_id=i['order_id']) print(re)
    # order_list = [ {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 2,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 0.7,
    # 'quantity': 20}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.52,
    # 'quantity': 10},] {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.53,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.54,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.55,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.56,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.57,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.58,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.59,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.60,
    # 'quantity': 10}, {'symbol': 'ADAUSDT', 'side': OrderSide.SELL, 'order_type': OrderType.LIMIT, 'price': 1.61,
    # 'quantity': 10} ] data = binance.place_batch_order(order_list=order_list) print('加工:\n', data)

    # data = binance.exchangeInfo()['exchangeFilters']
    # print(data)
    # data = binance.get_all_open_order()
    # a = 1
    # for id in data['data']:
    #     re = binance.cancel_order(symbol='ADAUSDT', order_id=id['order_id'])
    #     print(a)
    #     a +=1
    # data = binance.get_trade_history('LTCETH')
    # print('加工:\n', data)

    # # 1、查看某个币对的详情，并记录其报价规则
    # check_symbol_list = ['LSKUSDT']
    # for i in data['symbols']:
    #     if i['symbol'] in check_symbol_list:
    #         print('-' * 10)
    #         print(i)
    #         print('min_vol：', i['filters'][2]['minQty'])
    #         print('qty_precision：', i['filters'][2]['stepSize'])
    #         print('min_quote_vol：', i['filters'][3]['minNotional'])
    #         print('price_precision：', i['filters'][0]['tickSize'])
    # exit()
    # data = binance.get_order_book('ETHUSDT', limit=5)
    # print(data)
    # 获取K线
    # start_time = None
    # start_time = int(time.mktime(time.strptime('2021-10-01 08:00:00', "%Y-%m-%d %H:%M:%S")))

    #
    # exit()
    # # 获取最新价格
    # data = binance.get_latest_price(symbol=None)
    # print(data)
    # exit()

    # 获取账户信息---------------------------------------------------------------
    # 1-展示个别品种
    # data = binance.get_position_info()
    # #
    # print(data)
    # for d in data['balances']:
    #     # if d['asset'] in ['ETH', 'BTC', 'LTC', 'ADA', 'BNB', 'TRX', 'LINK']:
    #     if d['asset'] in ['USDT', 'KLAY']:
    #         print(d)

    # 2-展示全部品种
    # data = binance.get_position_info()
    # for d in data['balances']:
    #     print(d)
    # data = binance.get_account_info()
    # print(data)
    # ------------------------------------------------------------------------

    # 获取账户交易历史------------------------------------------------------------
    # import pandas as pd
    # import time
    #
    # pd.set_option("expand_frame_repr", False)
    # pd.set_option('display.max_rows', None)
    # symbol = 'IOTAUSDT'
    # data = binance.get_trade_history(symbol)
    # print(data)
    # # exit()
    # #
    # timelist = []
    # symbollist = []
    # fxlist = []
    # pricelist = []
    # qtylist = []
    # quoteqtylist = []
    # commissionlist = []
    # commission_asset_list = []
    # for i in data:
    #     timelist.append(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(str(i['time'])[0:-3]))))
    #     symbollist.append(i['symbol'])
    #     fx = 'buy' if i['isBuyer'] == True else 'sell'
    #     fxlist.append(fx)
    #     pricelist.append(i['price'])
    #     qtylist.append(i['qty'])
    #     quoteqtylist.append(i['quoteQty'])
    #     commissionlist.append(i['commission'])
    #     commission_asset_list.append(i['commissionAsset'])
    # dic = {}
    # dic['time'] = timelist
    # dic['symbol'] = symbollist
    # dic['fx'] = fxlist
    # dic['price'] = pricelist
    # dic['qty'] = qtylist
    # dic['quoteqty'] = quoteqtylist
    # dic['commission'] = commissionlist
    # dic['commissionAsset'] = commission_asset_list
    # df = pd.DataFrame(dic)
    # print(df)
    # df.to_csv(f'D:\\trade_history_{symbol}.csv')
    # exit()
    # ------------------------------------------------------------------------

    # 获取订单信息，可根据ID传入
    # data = binance.get_order(symbol='LTCETH', order_id='220350430')

    # 获取交易所全部币种信息--------------------
    # data = binance.exchangeInfo()
    # print(data)
    # # 1、查看某个币对的详情，并记录其报价规则
    # check_symbol_list = ['XLMUSDT', 'BCHUSDT', 'ADAUSDT']
    # for i in data['symbols']:
    #     if i['symbol'] in check_symbol_list:
    #         print('-' * 10)
    #         # print(i)
    #         print(i['symbol'])
    #         print('min_vol：', i['filters'][2]['minQty'])
    #         print('qty_precision：', i['filters'][2]['stepSize'])
    #         print('min_quote_vol：', i['filters'][3]['minNotional'])
    #         print('price_precision：', i['filters'][0]['tickSize'])
    #
    # exit()
    # print(data)
    # 报单测试
    # data = binance.place_order(symbol="ETHUSDT", side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=0.1, quote_quantity=None, price=5000)
    # print(data)
    # exit()

    # 挂单测试
    # data = binance.place_order(symbol="ETHBTC", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, quote_quantity=None, price=0.03)
    # 查询订单
    # data = binance.get_order(symbol="ETHBTC", order_id='1971206508')
    # 查询所有挂单
    # data = binance.get_all_open_order(symbol='ETHUSDT')

    # 撤销订单6756412012,6756423007
    # data = binance.cancel_order(symbol="ETHUSDT", order_id='6756423007')
    #
    # print(data)
    # exit()

    # 查询所有挂单
    # data = binance.get_all_open_order(symbol='XLMUSDT')
    # print(data)
    # exit()

    # 获取最新价格
    # data = float(binance.get_latest_price('ADAUSDT')['price'])

    # print(data)

    # 期货--------------------------------------------------------------------------------------------------------------

    # U本位-----------------------------------------------------------------------------------------------
    # binance = binance_future_u_http(key=key, secret=secret, proxy_host=proxy_host, proxy_port=proxy_port)

    # order_list = [
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.05, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.12, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.08, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.05, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.12, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None},
    #     {'symbol': 'ADAUSDT', 'side': OrderSide.BUY, 'order_type': OrderType.LIMIT, 'price': 1.08, 'quantity': 10,
    #      'position_side': PositionSide.LONG, 'quote_quantity': None}
    # ]
    # data = binance.place_batch_order(order_list=order_list)
    # print('加工:\n', data)

    # data = binance.get_all_open_order(symbol='ADAUSDT')
    # for i in data['data']:
    #     re = binance.cancel_order(symbol='ADAUSDT', order_id=i['order_id'])
    #     print(re)

    # # **************************** 期货U本位--客户账户设置↓ ****************************
    # contract = "BNB"+"USDT"
    # leverage_ratio = 2
    # #
    # # 1-设置和调整杠杆
    # data = binance.change_leverage(contract, leverage_ratio)
    # print(f"设置杠杆为:{leverage_ratio},交易所返回：{data}")
    # # 2-设置交易模式，双向还是单向(false是单向，true是双向）
    # data = binance.change_positionSide(dualSideType.TRUE)
    # print(f"设置持仓模式为双向,交易所返回：{data}")
    # # 3-设置保证金模式，(ISOLATED--逐仓，CROSSED--全仓)
    # data = binance.change_marginType(contract, marginType.ISOLATED)
    # print(f"设置持仓模式为逐仓,交易所返回：{data}")
    # #
    # # *************** 设置完成后查看设置结果 **********
    # print('设置完成，检查核对-----------------------------')
    # # 1-查看杠杆设置情况
    # data = binance.get_positionRisk_info(contract, PositionSide.LONG)
    # print('查询杠杆倍数：\n', data)
    # # 2-查询交易模式
    # data = binance.get_positionSide()
    # print('查询交易模式：\n', data)
    # # 3-查询保证金模式
    # data = binance.get_position_info()
    # print('查询保证金模式：\n')
    # for i in data['positions']:
    #     if i['symbol'] == contract:
    #         print(i)
    # exit()
    # **************************** 期货U本位--客户账户设置--结束 ****************************

    # 一、查询公共信息
    # 获取交易所全部币种信息
    # data = binance.exchangeInfo()
    # 获取K线
    # data = binance.get_kline('ETHUSDT', Interval.MINUTE_15)
    # print(data)
    # 获取最新价格
    # data = binance.get_latest_price('ETHUSDT')
    # print(data)
    # 测试获取深度信息(盘口信息）
    # data = binance.get_order_book(symbol='ETHUSDT', limit=5)
    # print(data)
    # 查询私密信息
    # 获取账户余额
    # data = binance.get_position_info()
    # print('usdt:', data['assets'][1])
    # 查询主要货币对剩余资产
    # data = binance.get_balance()
    # print(data)
    # 获取币对交易记录
    # symbol = 'XRP'+'USDT'
    # data=binance.get_trade_history(symbol=symbol)
    # print(data)
    # data.to_csv(f"D:\\{symbol}.csv")
    # exit()
    # 账户下单
    # data = binance.place_order(symbol="ETHUSDT", positionSide=PositionSide.SHORT, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.006, price=3333.71)
    # print(data)

    # print(data)
    # exit()

    # 币本位-----------------------------------------------------------------------------------------------
    # binance = binance_future_coin_http(key=key, secret=secret, proxy_host=proxy_host, proxy_port=proxy_port)
    # data = binance.place_order(symbol='ADAUSD',side=OrderSide.BUY, order_type=OrderType.LIMIT, position_side=PositionSide.LONG, quantity=1, price=1.1)
    # data = binance.exchangeInfo()
    # data = binance.get_balance_info()
    # print('加工:\n', data)
    # data = binance.get_kline(symbol='BTCUSD',interval=Interval.DAY_1)
    # print('加工:\n', data)

    # data = binance.get_24h_ticker(symbol='ETHUSD')
    # print('加工:\n', data)

    # data = binance.get_balance_info()
    # print('加工:\n', data)

    # data = binance.place_order(symbol='ADA')
    # print('加工:\n', data)

    # data = binance.change_margin_type(symbol='ETHUSD', marginType=marginType.ISOLATED)
    # print('加工:\n', data)

    # data = binance.change_position_margin(symbol='ETHUSD',quantity=10,type=positionMarginType.TWO, positionSide=PositionSide.LONG)
    # print('加工:\n', data)

    # data = binance.get_latest_price('ETHUSD_PERP')
    # print(data)
    #
    # # **************************** 期货币本位--客户账户设置↓ ****************************
    # contract = "ETHUSD_PERP"
    # leverage_ratio = 2
    # #
    # # 1-设置和调整杠杆
    # data = binance.change_leverage(contract, leverage_ratio)
    # print(f"设置杠杆为:{leverage_ratio},交易所返回：{data}")
    # # 2-设置交易模式，双向还是单向(false是单向，true是双向）
    # data = binance.change_positionSide(dualSideType.TRUE)
    # print(f"设置持仓模式为双向,交易所返回：{data}")
    # # 3-设置保证金模式，(ISOLATED--逐仓，CROSSED--全仓)
    # data = binance.change_marginType(contract, marginType.ISOLATED)
    # print(f"设置持仓模式为逐仓,交易所返回：{data}")
    # #
    # *************** 设置完成后查看设置结果 **********
    # print('设置完成，检查核对-----------------------------')
    # # 1-查看杠杆设置情况
    # data = binance.get_positionRisk_info(contract, PositionSide.LONG)
    # print('查询杠杆倍数：\n', data)
    # # 2-查询交易模式
    # data = binance.get_positionSide()
    # print('查询交易模式：\n', data)
    # # 3-查询保证金模式
    # data = binance.get_position_info()
    # print('查询保证金模式：\n')
    # for i in data['positions']:
    #     if i['symbol'] == contract:
    #         print(i)
    # exit()
    # **************************** 期货币本位--客户账户设置--结束 ****************************

    # 获取交易所全部币种信息--------------------
    # data = binance.exchangeInfo()
    # 1、查看某个币对的详情，并记录其报价规则
    # check_symbol_list = ['ETHUSD_PERP', 'BTCUSD_PERP']
    # for i in data['symbols']:
    #     if i['symbol'] in check_symbol_list:
    #         print('-' * 10)
    #         print(i['symbol'])
    #         print('min_vol：', i['filters'][2]['minQty'])
    #         print('max_vol：', i['filters'][2]['maxQty'])
    #         print('qty_precision：', i['filters'][2]['stepSize'])
    #         print('price_precision：', i['filters'][0]['tickSize'])

    # 测试获取深度信息(盘口信息）
    # data = binance.get_order_book(symbol='ETHUSD_PERP', limit=5)
    # 获取K线---------------------------------
    # data = binance.get_kline('ETHUSD_PERP', Interval.HOUR_1)
    # 测试查询最新价格-------------------------
    # data=binance.get_latest_price('ETHUSD_PERP')

    # 币划转（暂未开通权限无法测试）
    # data = binance.transfer_CoinFuture("ETH",0.0001)
    # 获取币对交易记录-------------------------
    # data = binance.get_trade_history(symbol='ETHUSD_PERP')
    # print(data)
    # exit()

    # 获取账户信息-----------------------------
    # 获取账户币种信息，可用资金、未平仓盈亏等等，可用资金为re['assets']里遍历获得dic['availableBalance']
    # 查询某个币本位资产数额
    # data = binance.get_position_info(symbol='ETH', type='asset')

    # 查询某个品种的持仓信息
    # data = binance.get_position_info(symbol='ETHUSD_PERP', type='positions')
    # print (data)
    # for d in data:
    #     if d['positionSide'] == 'LONG':
    #         print('-'*20)
    #         print('多头持仓数量：', d['positionAmt'])
    #         print(d)
    #     elif d['positionSide'] == 'SHORT':
    #         print('-' * 20)
    #         print('空头持仓数量：', d['positionAmt'])
    #         print(d)
    # exit()
    # print(data)

    # 获取账户风险信息（持仓信息等等）---------------
    # data = binance.get_positionRisk_info("ETHUSD_PERP", PositionSide.SHORT)
    # 获取订单信息----------------------------
    # data = binance.get_order('ETHUSD_PERP','7347214728')
    # 获取挂单信息---------------------------
    # data = binance.get_open_orders(symbol='ETHUSD_PERP')
    # 报单测试 币本位------------------------82105 - 75000 = 7105
    # data = binance.place_order(symbol="ETHUSD_PERP", positionSide=PositionSide.LONG, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=7642, price=3389.2)
    # print('报单回报:',data)
    # 查询账户余额
    # data=binance.get_balance()
    # print(data)
    # print('-'*20)
    # data = binance.get_position_info(symbol='ETHUSD_PERP', type='positions')
    # print(data)
    # exit()
    # 挂单测试
    # data = binance.place_order(symbol="ETHUSD_PERP", positionSide=PositionSide.SHORT,side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=1, price=3000)
    # 查询订单
    # data = binance.get_order(symbol="ETHUSD_PERP", order_id='18152247724')
    # 撤销订单
    # data = binance.cancel_order(symbol="ETHUSD_PERP", order_id=9045830981)

    # 更改持仓模式 之前默认false,现在也还是false--------------------
    # data = binance.change_positionSide(dualSideType.TRUE)
    # print(data)
    # 查询持仓模式 币本位(false是单向，true是双向）
    # data = binance.get_positionSide()

    # # 批量下单 (暂时用不到，不测试）
    # orderOne=binance.build_batch_order(symbol="ETHUSD_PERP", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1,price=2600,time_inforce="GTC")
    # orderTwo=binance.build_batch_order(symbol="ETHUSD_PERP", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1,price=2300,time_inforce="GTC")
    # batchOrders=[orderOne,orderTwo]
    # data= binance.place_batch_order(batchOrders)
    # 撤销当前订单
    # data = binance.cancel_order("ETHUSD_PERP","7326580584")
    # 撤销全部订单
    # data = binance.cancel_all_orders("ETHUSD_PERP")
    # 批量撤单
    # data = binance.cancel_batch_orders("ETHUSD_PERP",orderIdList=[6887649648])
    # 调整开仓杠杆
    # data = binance.change_leverage("ETHUSD_PERP",1)
    # 变换逐全仓模式 如果切换返回{'code': 200, 'message': 'success'}， 如果本身逐仓还要切换逐仓会报错告诉你no need to change marginType
    # 现在ETHUSD_PERP是逐仓模式
    # data = binance.change_marginType("ETHUSD_PERP",marginType.ISOLATED)
    # exit()
    # 调整逐仓保证金
    # data = binance.change_position_margin("ETHUSD_PERP",quantity="0.001",type=positionMarginType.ONE)
    # print(data)

    # 查询某个品种的持仓信息
    # data = binance.get_position_info(symbol='ETHUSD_PERP', type=None)
    # print(data)
    # for d in data:
    #     if d['positionSide'] == 'LONG':
    #         print('-'*20)
    #         print('多头持仓数量：', d['positionAmt'])
    #         print(d)
    #     elif d['positionSide'] == 'SHORT':
    #         print('-' * 20)
    #         print('空头持仓数量：', d['positionAmt'])
    #         print(d)

    # print(data)

    # exit()
