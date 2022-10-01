import logging
from datetime import datetime
import json
from realtrade.all_common.gateway.base_websocket import BaseWebsocket


# 现货WS
class binance_spot_data_websocket(BaseWebsocket):
    def __init__(self, ping_interval=20, on_tick_callback=None, on_tick_callback_list=None, proxy_host=None, proxy_port=None,
                 special_key=None, key=None, secret=None, exchange_name='binance', market_type='spot'):
        # 设置websocket的基础地址
        host = "wss://stream.binance.com:9443/stream?streams="
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.key = key
        self.secret = secret
        self.special_key = special_key
        self.exchange_name = exchange_name
        self.market_type = market_type
        # 引用父类里的内容
        super(binance_spot_data_websocket, self).__init__(host=host, ping_interval=ping_interval, proxy_host=proxy_host, proxy_port=proxy_port)
        # 绑定回调启动的函数
        self.on_tick_callback = on_tick_callback
        self.on_tick_callback_list = on_tick_callback_list
        # 初始设置订阅品种，利用set函数增加需要订阅的数据，以免重复订阅
        # 利用symbol绑定set方法,便于后续直接增加币种
        self.symbols = set()
        # self.symbols.add('btcusdt')
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        self.tick_book = {'ask': None, 'ask_vol': None, 'bid': None, 'bid_vol': None}
        self.books = {}
        self.channel_dic = {'order_book': 'order_book', 'order_book_update': 'order_book_update', 'public_trade': 'trade', 'ticker': 'bookTicker', 'my_trade': 'my_trade'}
        self.first_get_books = 0
        self.book_num = 0
        self.record = 'Not yet'

    def on_open(self):
        self.first_get_books = 0
        self.books = {}
        print(f"binance spot ws open at:{datetime.now()}")

    def on_close(self):
        print(f"binance spot ws close at:{datetime.now()}")

    # ws连接以后，如有tick信息，处理收到的tick信息，并将该tick信息传入策略里进行计算
    def on_msg(self, data: str):
        # print('原始:', data)
        # 用json转换信息
        json_msg = json.loads(data)
        # print(json_msg)
        # 读取事件类型
        if 'ping' in json_msg:
            self.record = json_msg
        stream = json_msg["stream"]
        # print(f"stream:{stream}")
        # 读取事件内容
        data = json_msg["data"]
        # print(f"data:{data}")
        if len(stream.split("@")) == 3:
            symbol, channel, speed = stream.split("@")
        elif len(stream.split("@")) > 1:
            symbol, channel = stream.split("@")
        else:
            channel = 'my_trade'
            symbol = self.record
        # 如果订阅的是10档及以上的深度信息：
        if channel in ['depth5', 'depth10', 'depth20']:
            self.books['symbol'] = symbol.upper()
            self.books['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            self.books['asks'] = [[float(i[0]), float(i[1])] for i in data['asks']]
            self.books['bids'] = [[float(i[0]), float(i[1])] for i in data['bids']]

            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'trade':
            ticker = {
                "public_trade": True,
                "symbol": data['s'].upper(),
                "datetime": datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "price": float(data['p']),
                "qty": float(data['q'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback([ticker])
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback([ticker])

        if channel == 'bookTicker':
            ticker = {
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                "bid": float(data['b']),
                "ask": float(data['a'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(ticker)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(ticker)

        if channel == 'depth':

            if self.first_get_books == 0:
                logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http", fromlist=(f"gateway.{self.exchange_name}_http",)), f"{self.exchange_name}_{self.market_type}_http")
                http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                re = http_client.get_order_book(symbol=symbol.upper())
                if re['success']:
                    self.books = re['data']
                else:
                    print('获取盘口信息失败，返回：', re)
                self.first_get_books = 1

            # 进行数据维护
            seqnum = float(data['E'])
            if seqnum > self.book_num:
                # 更新记录序号
                self.book_num = seqnum
                # 更新时间：
                self.books['datetime'] = datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")

                # 本地副本维护
                # 如果asks有更新：
                if 'a' in data:
                    if len(data['a']) > 0:
                        # 新方法
                        del_price_list = []
                        other_list = []
                        for d in data['a']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=False)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=False)

                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['asks'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['asks'][i][0] == float(del_price):
                                    del self.books['asks'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        aski = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['asks'][0][0] > float(i[0]):
                                self.books['asks'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['asks'][-1][0] < float(i[0]):
                                self.books['asks'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['asks'])
                            if aski < datalength:
                                # 遍历替换或插入
                                for j in range(aski, datalength):
                                    # 替换数据：
                                    if self.books['asks'][j][0] == float(i[0]):
                                        self.books['asks'][j] = [float(i[0]), float(i[1])]
                                        aski = j
                                        break
                                    # 插入数据:
                                    if self.books['asks'][j][0] > float(i[0]):
                                        self.books['asks'].insert(j, [float(i[0]), float(i[1])])
                                        aski = j
                                        break
                if 'b' in data:
                    if len(data['b']) > 0:
                        del_price_list = []
                        other_list = []
                        for d in data['b']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=True)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=True)
                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['bids'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['bids'][i][0] == float(del_price):
                                    del self.books['bids'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        bidi = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['bids'][0][0] < float(i[0]):
                                self.books['bids'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['bids'][-1][0] > float(i[0]):
                                self.books['bids'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['bids'])
                            if bidi < datalength:
                                # 遍历替换或插入
                                for j in range(bidi, datalength):
                                    # 替换数据：
                                    if self.books['bids'][j][0] == float(i[0]):
                                        self.books['bids'][j] = [float(i[0]), float(i[1])]
                                        bidi = j
                                        break
                                    # 插入数据:
                                    if self.books['bids'][j][0] < float(i[0]):
                                        self.books['bids'].insert(j, [float(i[0]), float(i[1])])
                                        bidi = j
                                        break

            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'my_trade':
            re_dic = {}
            if data['e'] == 'executionReport':
                order_time = datetime.fromtimestamp(float(data['T']) / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")
                fee_coin = data['N']
                fee = float(data['n'])
                order_type = data['o']
                id = data['i']
                sym = data['s']
                side = data['S']
                qty = float(data['q'])
                price = float(data['p'])
                status = data['X'].lower()
                re_dic = {
                    'my_trade': True,
                    'symbol': sym,
                    'side': side,
                    'price': price,
                    'qty': qty,
                    'order_type': order_type.lower(),
                    'status': status.lower(),
                    'order_id': id,
                    'fee_coin': fee_coin,
                    'fee': fee,
                    'base_asset_total': '',
                    'base_asset_available': '',
                    'quote_asset_total': '',
                    'quote_asset_available': ''
                }
            if len(re_dic) == 0:
                return
            if self.on_tick_callback:
                self.on_tick_callback(re_dic)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(re_dic)

    def on_error(self, exception_type: type, exception_value: Exception, tb):
        print(f"binance spot ws触发异常，状态码：{exception_type}，信息：{exception_value}")

    # 设置订阅的品种信息，若当前为订阅状态，先关闭任务线程，增加品种后再订阅，然后直接开始任务
    def subscribe(self, symbol, channel_list):
        for d in channel_list:
            if d.split('?')[0] not in self.channel_dic.keys():
                print("\033[0;31;40m输入频道名不正确，请检查\033[0m")
                return
        # 根据初始设置的品种，增加新品种，因为symbol绑定了set方法，直接ADD不会重复
        for i in symbol:
            self.symbols.add(i)
        # _active继承自base_websocket，如果on_open以后就为True，若现在时连接状态，关闭连接，关闭进程，
        # 币安连接规则：单次订阅，订阅后不能临时直接增减，需要停止后重新连接
        if self._active:
            self.stop()
            self.join()

        channels = []
        para = '20'
        t_para = '100ms'
        # 根据需要订阅品种，加入channels中，
        for symbol in self.symbols:
            print(f"{symbol}：订阅数据：", end='')
            for subchannel in channel_list:
                print(f"{subchannel}...", end='')
                sub = subchannel.split('?')
                # print(sub)
                if len(sub) > 1:
                    if len(sub[1]) > 0:
                        subchannel = self.channel_dic[sub[0]]
                        para = sub[1].split('_')[0]
                        t_para = sub[1].split('_')[1]
                    else:
                        subchannel = self.channel_dic[sub[0]]
                if subchannel == 'trade':
                    channels.append(symbol.lower() + "@trade")
                if subchannel == 'order_book':
                    channels.append(symbol.lower() + f"@depth{para}@{t_para}")
                if subchannel == 'order_book_update':
                    channels.append(symbol.lower() + f"@depth@{t_para}")
                if subchannel == 'my_trade':
                    self.record = symbol
                    logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http",
                                                    fromlist=(f"gateway.{self.exchange_name}_http",)),
                                         f"{self.exchange_name}_{self.market_type}_http")
                    http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key,
                                             proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                    re = http_client.make_listen_key()
                    channels.append(re['listenKey'])
                if subchannel == 'bookTicker':
                    channels.append(symbol.lower() + "@bookTicker")

        # 生成订阅连接
        self.host += '/'.join(channels)
        # print(self.host)
        # 启动主任务，调取base_websocket里的start函数
        self.start()


# 期货U本位
class binance_future_u_data_websocket(BaseWebsocket):
    def __init__(self, ping_interval=20, on_tick_callback=None, on_tick_callback_list=None, proxy_host=None, proxy_port=None,
                 special_key=None, key=None, secret=None, exchange_name='binance', market_type='future_u'):
        # 设置websocket的基础地址
        host = "wss://fstream.binance.com/stream?streams="
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.key = key
        self.secret = secret
        self.special_key = special_key
        self.exchange_name = exchange_name
        self.market_type = market_type
        # 引用父类里的内容
        super(binance_future_u_data_websocket, self).__init__(host=host, ping_interval=ping_interval, proxy_host=proxy_host, proxy_port=proxy_port)
        # 绑定回调启动的函数
        self.on_tick_callback = on_tick_callback
        self.on_tick_callback_list = on_tick_callback_list
        # 初始设置订阅品种，利用set函数增加需要订阅的数据，以免重复订阅
        # 利用symbol绑定set方法,便于后续直接增加币种
        self.symbols = set()
        # self.symbols.add('btcusdt')
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        self.tick_book = {'ask': None, 'ask_vol': None, 'bid': None, 'bid_vol': None}
        self.books = {}
        self.channel_dic = {'order_book': 'order_book', 'order_book_update': 'order_book_update', 'public_trade': 'aggTrade', 'ticker': 'bookTicker', 'my_trade': 'my_trade'}
        self.first_get_books = 0
        self.book_num = 0
        self.record = 'Not yet'

    def on_open(self):
        self.first_get_books = 0
        self.books = {}
        print(f"binance future_u ws open at:{datetime.now()}")

    def on_close(self):
        print(f"binance future_u ws close at:{datetime.now()}")

    # ws连接以后，如有tick信息，处理收到的tick信息，并将该tick信息传入策略里进行计算
    def on_msg(self, data: str):
        # print('原始:', data)
        # 用json转换信息
        json_msg = json.loads(data)
        # 读取事件类型
        if 'ping' in json_msg:
            self.record = json_msg
        stream = json_msg["stream"]
        # print(f"stream:{stream}")
        # 读取事件内容
        data = json_msg["data"]
        # print(f"data:{data}")
        if len(stream.split("@")) == 3:
            symbol, channel, speed = stream.split("@")
        elif len(stream.split("@")) > 1:
            symbol, channel = stream.split("@")
        else:
            channel = 'my_trade'
            symbol = self.record
        # 如果订阅的是10档及以上的深度信息：
        if channel in ['depth5', 'depth10', 'depth20']:
            self.books['symbol'] = symbol.upper()
            self.books['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            self.books['asks'] = [[float(i[0]), float(i[1])] for i in data['a']]
            self.books['bids'] = [[float(i[0]), float(i[1])] for i in data['b']]

            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'aggTrade':
            ticker = {
                "public_trade": True,
                "symbol": data['s'].upper(),
                "datetime": datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "price": float(data['p']),
                "qty": float(data['q'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback([ticker])
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback([ticker])

        if channel == 'bookTicker':
            tk = {
                "datetime": datetime.fromtimestamp(data['T'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "bid": float(data['b']),
                "ask": float(data['a'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(tk)
            # 多个策略回调
            if self.on_tick_callback_list:
                self.on_tick_callback(tk)

        if channel == 'depth':

            if self.first_get_books == 0:
                logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http", fromlist=(f"gateway.{self.exchange_name}_http",)), f"{self.exchange_name}_{self.market_type}_http")
                http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                re = http_client.get_order_book(symbol=symbol.upper())
                if re['success']:
                    self.books = re['data']
                else:
                    print('获取盘口信息失败，返回：', re)
                self.first_get_books = 1

            # 进行数据维护
            seqnum = float(data['E'])
            if seqnum > self.book_num:
                # 更新记录序号
                self.book_num = seqnum
                # 更新时间：
                self.books['datetime'] = datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")

                # 本地副本维护
                # 如果asks有更新：
                if 'a' in data:
                    if len(data['a']) > 0:
                        # 新方法
                        del_price_list = []
                        other_list = []
                        for d in data['a']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=False)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=False)

                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['asks'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['asks'][i][0] == float(del_price):
                                    del self.books['asks'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        aski = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['asks'][0][0] > float(i[0]):
                                self.books['asks'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['asks'][-1][0] < float(i[0]):
                                self.books['asks'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['asks'])
                            if aski < datalength:
                                # 遍历替换或插入
                                for j in range(aski, datalength):
                                    # 替换数据：
                                    if self.books['asks'][j][0] == float(i[0]):
                                        self.books['asks'][j] = [float(i[0]), float(i[1])]
                                        aski = j
                                        break
                                    # 插入数据:
                                    if self.books['asks'][j][0] > float(i[0]):
                                        self.books['asks'].insert(j, [float(i[0]), float(i[1])])
                                        aski = j
                                        break
                if 'b' in data:
                    if len(data['b']) > 0:
                        del_price_list = []
                        other_list = []
                        for d in data['b']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=True)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=True)
                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['bids'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['bids'][i][0] == float(del_price):
                                    del self.books['bids'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        bidi = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['bids'][0][0] < float(i[0]):
                                self.books['bids'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['bids'][-1][0] > float(i[0]):
                                self.books['bids'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['bids'])
                            if bidi < datalength:
                                # 遍历替换或插入
                                for j in range(bidi, datalength):
                                    # 替换数据：
                                    if self.books['bids'][j][0] == float(i[0]):
                                        self.books['bids'][j] = [float(i[0]), float(i[1])]
                                        bidi = j
                                        break
                                    # 插入数据:
                                    if self.books['bids'][j][0] < float(i[0]):
                                        self.books['bids'].insert(j, [float(i[0]), float(i[1])])
                                        bidi = j
                                        break

            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'my_trade':
            re_dic = {}
            if data['e'] == 'ORDER_TRADE_UPDATE':
                re_dic = {
                    'my_trade': True,
                    'symbol': data['o']['s'],
                    'side': data['o']['S'].lower(),
                    'price': float(data['o']['p']) if float(data['o']['p']) > 0 else float(data['o']['ap']),
                    'qty': float(data['o']['q']) if float(data['o']['p']) > 0 else float(data['o']['z']),
                    'order_type': data['o']['o'].lower(),
                    'status': data['o']['X'].lower(),
                    'order_id': data['o']['i'],
                    'fee_coin': data['o']['N'] if 'N' in data['o'] else None,
                    'fee': float(data['o']['n']) if 'n' in data['o'] else None,
                    'base_asset_total': '',
                    'base_asset_available': '',
                    'quote_asset_total': '',
                    'quote_asset_available': ''
                }
            if len(re_dic) == 0:
                return
            if self.on_tick_callback:
                self.on_tick_callback(re_dic)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(re_dic)

    def on_error(self, exception_type: type, exception_value: Exception, tb):
        print(f"binance future_u ws触发异常，状态码：{exception_type}，信息：{exception_value}")

    # 设置订阅的品种信息，若当前为订阅状态，先关闭任务线程，增加品种后再订阅，然后直接开始任务
    def subscribe(self, symbol, channel_list):
        for d in channel_list:
            if d.split('?')[0] not in self.channel_dic.keys():
                print("\033[0;31;40m输入频道名不正确，请检查\033[0m")
                return
        # 根据初始设置的品种，增加新品种，因为symbol绑定了set方法，直接ADD不会重复
        for i in symbol:
            self.symbols.add(i)
        # _active继承自base_websocket，如果on_open以后就为True，若现在时连接状态，关闭连接，关闭进程，
        # 币安连接规则：单次订阅，订阅后不能临时直接增减，需要停止后重新连接
        if self._active:
            self.stop()
            self.join()

        channels = []
        para = '20'
        t_para = '100ms'
        # 根据需要订阅品种，加入channels中，
        for symbol in self.symbols:
            print(f"{symbol}：订阅数据：", end='')
            for subchannel in channel_list:
                print(f"{subchannel}...", end='')
                sub = subchannel.split('?')
                # print(sub)
                if len(sub) > 1:
                    if len(sub[1]) > 0:
                        subchannel = self.channel_dic[sub[0]]
                        para = sub[1].split('_')[0]
                        t_para = sub[1].split('_')[1]
                    else:
                        subchannel = self.channel_dic[sub[0]]
                if subchannel == 'aggTrade':
                    channels.append(symbol.lower() + "@aggTrade")
                if subchannel == 'order_book':
                    channels.append(symbol.lower() + f"@depth{para}@{t_para}")
                if subchannel == 'order_book_update':
                    channels.append(symbol.lower() + f"@depth@{t_para}")
                if subchannel == 'my_trade':
                    self.record = symbol
                    logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http", fromlist=(f"gateway.{self.exchange_name}_http",)), f"{self.exchange_name}_{self.market_type}_http")
                    http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                    re = http_client.make_listen_key()
                    channels.append(re['listenKey'])
                if subchannel == 'bookTicker':
                    channels.append(symbol.lower() + "@bookTicker")

        # 生成订阅连接
        self.host += '/'.join(channels)
        # print(self.host)
        # 启动主任务，调取base_websocket里的start函数
        self.start()


# 期货币本位
class binance_future_coin_data_websocket(BaseWebsocket):
    def __init__(self, ping_interval=20, on_tick_callback=None, on_tick_callback_list=None, proxy_host=None, proxy_port=None,
                 special_key=None, key=None, secret=None, exchange_name='binance', market_type='future_coin'):
        # 设置websocket的基础地址
        host = "wss://dstream.binance.com/stream?streams="
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.key = key
        self.secret = secret
        self.special_key = special_key
        self.exchange_name = exchange_name
        self.market_type = market_type
        # 引用父类里的内容
        super(binance_future_coin_data_websocket, self).__init__(host=host, ping_interval=ping_interval, proxy_host=proxy_host, proxy_port=proxy_port)
        # 绑定回调启动的函数
        self.on_tick_callback = on_tick_callback
        self.on_tick_callback_list = on_tick_callback_list
        # 初始设置订阅品种，利用set函数增加需要订阅的数据，以免重复订阅
        # 利用symbol绑定set方法,便于后续直接增加币种
        self.symbols = set()
        # self.symbols.add('btcusdt')
        # 调用日志输出模块，初始化
        self.logger = logging.getLogger(__name__)
        self.tick_book = {'ask': None, 'ask_vol': None, 'bid': None, 'bid_vol': None}
        self.books = {}
        self.channel_dic = {'order_book': 'order_book', 'order_book_update': 'order_book_update', 'public_trade': 'aggTrade', 'ticker': 'bookTicker', 'my_trade': 'my_trade'}
        self.first_get_books = 0
        self.book_num = 0
        self.record = 'Not yet'

    def on_open(self):
        self.first_get_books = 0
        self.books = {}
        print(f"binance future_coin ws open at:{datetime.now()}")

    def on_close(self):
        print(f"binance future_coin ws close at:{datetime.now()}")

    # ws连接以后，如有tick信息，处理收到的tick信息，并将该tick信息传入策略里进行计算
    def on_msg(self, data: str):
        # print('原始:', data)
        # 用json转换信息
        json_msg = json.loads(data)
        # 读取事件类型
        if 'ping' in json_msg:
            self.record = json_msg
        stream = json_msg["stream"]
        # print(f"stream:{stream}")
        # 读取事件内容
        data = json_msg["data"]
        # print(f"data:{data}")
        if len(stream.split("@")) == 3:
            symbol, channel, speed = stream.split("@")
        elif len(stream.split("@")) > 1:
            symbol, channel = stream.split("@")
        else:
            channel = 'my_trade'
            symbol = self.record
        # 如果订阅的是10档及以上的深度信息：
        if channel in ['depth5', 'depth10', 'depth20']:
            self.books['symbol'] = symbol.upper()
            self.books['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            self.books['asks'] = [[float(i[0]), float(i[1])] for i in data['a']]
            self.books['bids'] = [[float(i[0]), float(i[1])] for i in data['b']]

            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'aggTrade':
            ticker = {
                "public_trade": True,
                "symbol": data['s'].upper(),
                "datetime": datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "price": float(data['p']),
                "qty": float(data['q'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback([ticker])
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback([ticker])

        if channel == 'bookTicker':
            tk = {
                "datetime": datetime.fromtimestamp(data['T'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f"),
                "bid": float(data['b']),
                "ask": float(data['a'])
            }
            # 如果传入了策略，则直接调用该策略，同时把ticker传入策略里
            if self.on_tick_callback:
                self.on_tick_callback(tk)
            # 多个策略回调
            if self.on_tick_callback_list:
                self.on_tick_callback(tk)

        if channel == 'depth':
            if self.first_get_books == 0:
                logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http", fromlist=(f"gateway.{self.exchange_name}_http",)), f"{self.exchange_name}_{self.market_type}_http")
                http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                re = http_client.get_order_book(symbol=symbol.upper())
                if re['success']:
                    self.books = re['data']
                else:
                    print('获取盘口信息失败，返回：', re)
                self.first_get_books = 1

            # 进行数据维护
            seqnum = float(data['E'])
            if seqnum > self.book_num:
                # 更新记录序号
                self.book_num = seqnum
                # 更新时间：
                self.books['datetime'] = datetime.fromtimestamp(data['E'] / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")

                # 本地副本维护
                # 如果asks有更新：
                if 'a' in data:
                    if len(data['a']) > 0:
                        # 新方法
                        del_price_list = []
                        other_list = []
                        for d in data['a']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=False)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=False)

                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['asks'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['asks'][i][0] == float(del_price):
                                    del self.books['asks'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        aski = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['asks'][0][0] > float(i[0]):
                                self.books['asks'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['asks'][-1][0] < float(i[0]):
                                self.books['asks'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['asks'])
                            if aski < datalength:
                                # 遍历替换或插入
                                for j in range(aski, datalength):
                                    # 替换数据：
                                    if self.books['asks'][j][0] == float(i[0]):
                                        self.books['asks'][j] = [float(i[0]), float(i[1])]
                                        aski = j
                                        break
                                    # 插入数据:
                                    if self.books['asks'][j][0] > float(i[0]):
                                        self.books['asks'].insert(j, [float(i[0]), float(i[1])])
                                        aski = j
                                        break
                if 'b' in data:
                    if len(data['b']) > 0:
                        del_price_list = []
                        other_list = []
                        for d in data['b']:
                            if float(d[1]) == 0:
                                del_price_list.append(d[0])
                            else:
                                other_list.append([d[0], d[1]])
                        # 排序
                        del_price_list = sorted(del_price_list, key=lambda r: float(r), reverse=True)
                        other_list = sorted(other_list, key=lambda r: float(r[0]), reverse=True)
                        # 1-先执行：删除任务
                        use_i = 0
                        datalength = len(self.books['bids'])
                        for del_price in del_price_list:
                            for i in range(max(use_i, 0), datalength):
                                if self.books['bids'][i][0] == float(del_price):
                                    del self.books['bids'][i]
                                    use_i = i - 1
                                    datalength -= 1
                                    break

                        # 2-再执行：增、改
                        bidi = 0
                        for i in other_list:
                            # 更新最小的ask时：
                            if self.books['bids'][0][0] < float(i[0]):
                                self.books['bids'].insert(0, [float(i[0]), float(i[1])])
                                continue
                            # 更新最大的ask时：
                            if self.books['bids'][-1][0] > float(i[0]):
                                self.books['bids'].append([float(i[0]), float(i[1])])
                                continue

                            datalength = len(self.books['bids'])
                            if bidi < datalength:
                                # 遍历替换或插入
                                for j in range(bidi, datalength):
                                    # 替换数据：
                                    if self.books['bids'][j][0] == float(i[0]):
                                        self.books['bids'][j] = [float(i[0]), float(i[1])]
                                        bidi = j
                                        break
                                    # 插入数据:
                                    if self.books['bids'][j][0] < float(i[0]):
                                        self.books['bids'].insert(j, [float(i[0]), float(i[1])])
                                        bidi = j
                                        break

            if self.on_tick_callback:
                self.on_tick_callback(self.books)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(self.books)

        if channel == 'my_trade':
            re_dic = {}
            if data['e'] == 'ORDER_TRADE_UPDATE':
                re_dic = {
                    'my_trade': True,
                    'symbol': data['o']['s'],
                    'side': data['o']['S'].lower(),
                    'price': float(data['o']['p']) if float(data['o']['p']) > 0 else float(data['o']['ap']),
                    'qty': float(data['o']['q']) if float(data['o']['p']) > 0 else float(data['o']['z']),
                    'order_type': data['o']['o'].lower(),
                    'status': data['o']['X'].lower(),
                    'order_id': data['o']['i'],
                    'fee_coin': data['o']['N'] if 'N' in data['o'] else None,
                    'fee': float(data['o']['n']) if 'n' in data['o'] else None,
                    'base_asset_total': '',
                    'base_asset_available': '',
                    'quote_asset_total': '',
                    'quote_asset_available': ''
                }
            if len(re_dic) == 0:
                return
            if self.on_tick_callback:
                self.on_tick_callback(re_dic)
            # 多个策略回调
            if self.on_tick_callback_list:
                for callback in self.on_tick_callback_list:
                    callback(re_dic)

    def on_error(self, exception_type: type, exception_value: Exception, tb):
        print(f"binance future_coin ws触发异常，状态码：{exception_type}，信息：{exception_value}")

    # 设置订阅的品种信息，若当前为订阅状态，先关闭任务线程，增加品种后再订阅，然后直接开始任务
    def subscribe(self, symbol, channel_list):
        for d in channel_list:
            if d.split('?')[0] not in self.channel_dic.keys():
                print("\033[0;31;40m输入频道名不正确，请检查\033[0m")
                return
        # 根据初始设置的品种，增加新品种，因为symbol绑定了set方法，直接ADD不会重复
        for i in symbol:
            self.symbols.add(i)
        # _active继承自base_websocket，如果on_open以后就为True，若现在时连接状态，关闭连接，关闭进程，
        # 币安连接规则：单次订阅，订阅后不能临时直接增减，需要停止后重新连接
        if self._active:
            self.stop()
            self.join()

        channels = []
        para = '20'
        t_para = '100ms'
        # 根据需要订阅品种，加入channels中，
        for symbol in self.symbols:
            print(f"{symbol}：订阅数据：", end='')
            for subchannel in channel_list:
                print(f"{subchannel}...", end='')
                sub = subchannel.split('?')
                # print(sub)
                if len(sub) > 1:
                    if len(sub[1]) > 0:
                        subchannel = self.channel_dic[sub[0]]
                        para = sub[1].split('_')[0]
                        t_para = sub[1].split('_')[1]
                    else:
                        subchannel = self.channel_dic[sub[0]]
                if subchannel == 'aggTrade':
                    channels.append(symbol.lower() + "@aggTrade")
                if subchannel == 'order_book':
                    channels.append(symbol.lower() + f"@depth{para}@{t_para}")
                if subchannel == 'order_book_update':
                    channels.append(symbol.lower() + f"@depth@{t_para}")
                if subchannel == 'my_trade':
                    self.record = symbol
                    logic_http = getattr(__import__(f"realtrade.all_common.gateway.{self.exchange_name}_http", fromlist=(f"gateway.{self.exchange_name}_http",)), f"{self.exchange_name}_{self.market_type}_http")
                    http_client = logic_http(key=self.key, secret=self.secret, special_key=self.special_key, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
                    re = http_client.make_listen_key()
                    channels.append(re['listenKey'])
                if subchannel == 'bookTicker':
                    channels.append(symbol.lower() + "@bookTicker")

        # 生成订阅连接
        self.host += '/'.join(channels)
        # print(self.host)
        # 启动主任务，调取base_websocket里的start函数
        self.start()


def test(data):
    print('data:')
    print('asks', data['asks'][0:5])
    print('bids', data['bids'][0:5])

def test2(data):
    print('test2:')
    print(data)


if __name__ == '__main__':
    # 如有代理，设置代理
    name = 'test'
    key = ""
    secret = ''
    proxy_host = '192.168.1.31'
    proxy_port = 7078
    special_key = None

    # 现货
    ws1 = binance_spot_data_websocket(on_tick_callback=test, proxy_host=proxy_host, proxy_port=proxy_port, key=key, secret=secret, special_key=special_key)
    # ws1 = binance_future_u_data_websocket(on_tick_callback=test, proxy_host=proxy_host, proxy_port=proxy_port, key=key, secret=secret, special_key=special_key)
    # ws1 = binance_future_coin_data_websocket(on_tick_callback=test, proxy_host=proxy_host, proxy_port=proxy_port, key=key, secret=secret, special_key=special_key)
    # ws1.subscribe('all_symbol', ['all_tick'])

    # 期货U本位
    symbol_list = ['ETHUSDT']
    channel_list = ['my_trade?']
    ws1.subscribe(symbol_list, channel_list)

    # tick数据
    # ws2.subscribe(symbol_list, ['ticker?'])

