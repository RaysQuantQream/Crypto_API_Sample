from realtrade.all_common.util.utility import load_json_info, save_json_info, save_json_info_No_Indent, MyEncoder, NoIndent

import json


class exchange_info_update(object):

    def __init__(self):
        # self.proxy_host = '192.168.1.31'
        # self.proxy_port = 7078
        self.proxy_host = '192.168.1.4'
        self.proxy_port = 4780

    def split_name(self, name):
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

    def get_exchange_format(self, exchange_name, market_type):
        path = f"D:/quant/realtrade/all_config_info/exchange_info/exchange_info_{exchange_name}"
        format_text = load_json_info(path)[f"{exchange_name}_{market_type}"]["format"]
        return format_text

    def make_trade_name(self, format_rule, elements):

        if len(elements) == 2:
            trade_name = format_rule.format(elements[0], elements[1])
        else:
            trade_name = format_rule.format(elements[0], elements[1], elements[2])
            if 'SWAP' in trade_name:
                if not elements[2] == 'PERP':
                    trade_name.replace('SWAP', elements[2])
        return trade_name

    def update_info(self, exchange_name_list, symbol_list, market_type):

        for exchange_name in exchange_name_list:
            real_list = []
            for symbol in symbol_list:
                elements = self.split_name(name=symbol)
                format_rule = self.get_exchange_format(exchange_name=exchange_name, market_type=market_type)
                trade_name = self.make_trade_name(format_rule=format_rule, elements=elements)
                real_list.append(trade_name)
            path = f"D:/quant/realtrade/all_config_info/exchange_info/exchange_info_{exchange_name}"
            file = load_json_info(path)
            logic_http = getattr(__import__(f"realtrade.all_common.gateway.{exchange_name}_http", fromlist=(f"gateway.{exchange_name}_http",)), f"{exchange_name}_{market_type}_http")
            http_client = logic_http(key=None, secret=None, special_key=None, proxy_host=self.proxy_host, proxy_port=self.proxy_port)
            info_dic = http_client.get_exchange_info(symbol_list=real_list, need_change_result=True)

            file[f'{exchange_name}_{market_type}'].update(info_dic)
            for key in file.keys():
                for sub in file[key].keys():
                    file[key][sub] = NoIndent(file[key][sub])
            save_json_info_No_Indent(path, file)
            print(f'{exchange_name}数据更新成功')


if __name__ == '__main__':
    #temp
    exchange_name_list = ['aboard']
    symbol_list = ['ETH-USDC_PERP', 'AAVE-USDC_PERP', 'ANC-USDC_PERP', 'APE-USDC_PERP', 'BTC-USDC_PERP', 'LINK-USDC_PERP', 'LUNA-USDC_PERP', 'UNI-USDC_PERP', 'SUSHI-USDC_PERP']
    #spot
    # exchange_name_list = ['binance', 'ascendex', 'bit', 'bitmart', 'bitwell', 'bybit', 'coinbase', 'ftx', 'gate', 'kucoin', 'mexc', 'okex', 'woo']
    # symbol_list = ['BTC-USDT', 'ETH-USDT', 'MATIC-USDT', 'KLAY-USDT', 'SOL-USDT', 'XLM-USDT', 'BNB-BTC', 'LUNA-USDT', 'ONE-USDT', 'NEAR-USDT', 'FLOW-USDT', 'CRV-USDT', 'FTM-USDT',
    #                    'BCH-USDT', 'ADA-USDT', 'CKB-USDT', 'LINA-USDT', 'IOTA-USDT', 'LSK-USDT', 'PHBT-USDT', 'ATOM-USDT', 'LINK-USDT', 'PHB-BTC', 'JOE-USDT', 'DOT-USDT',
    #                    'AVAX-USDT', 'RAY-USDT', 'ETC-USDT', 'ALGO-USDT', 'FTT-USDT', 'HNT-USDT', 'DYDX-USDT', 'WOO-USDT', 'MANA-USDT', 'SAND-USDT', 'GALA-USDT', 'DOGE-USDT','AAVE-USDT', 'BNB-USDT', 'KDA-USDT', 'IMX-USDT']

    # future_u
    # exchange_name_list = ['binance', 'ascendex', 'bitwell', 'ftx', 'gate', 'kucoin', 'mexc', 'okex', 'woo']
    # symbol_list = ['BTC-USDT_PERP', 'ETH-USDT_PERP', 'MATIC-USDT_PERP', 'KLAY-USDT_PERP', 'SOL-USDT_PERP', 'XLM-USDT_PERP',
    #                'BNB-BTC_PERP', 'LUNA-USDT_PERP', 'ONE-USDT_PERP', 'NEAR-USDT_PERP', 'FLOW-USDT_PERP', 'CRV-USDT_PERP',
    #                'FTM-USDT_PERP', 'BCH-USDT_PERP', 'ADA-USDT_PERP', 'CKB-USDT_PERP', 'LINA-USDT_PERP', 'IOTA-USDT_PERP',
    #                'LSK-USDT_PERP', 'PHBT-USDT_PERP', 'ATOM-USDT_PERP', 'LINK-USDT_PERP', 'PHB-BTC_PERP', 'JOE-USDT_PERP',
    #                'DOT-USDT_PERP', 'AVAX-USDT_PERP', 'RAY-USDT_PERP', 'ETC-USDT_PERP', 'ALGO-USDT_PERP', 'FTT-USDT_PERP',
    #                'HNT-USDT_PERP', 'DYDX-USDT_PERP', 'WOO-USDT_PERP', 'MANA-USDT_PERP', 'SAND-USDT_PERP', 'GALA-USDT_PERP',
    #                'DOGE-USDT_PERP', 'AAVE-USDT_PERP', 'BNB-USDT_PERP', 'KDA-USDT_PERP', 'IMX-USDT_PERP']

    #future_coin
    # exchange_name_list = ['binance', 'kucoin', 'okex']
    # symbol_list = ['BTC-USD_PERP', 'ETH-USD_PERP', 'MATIC-USD_PERP', 'KLAY-USD_PERP', 'SOL-USD_PERP', 'XLM-USD_PERP', 'BNB-BTC_PERP',
    #                'LUNA-USD_PERP', 'ONE-USD_PERP', 'NEAR-USD_PERP', 'FLOW-USD_PERP', 'CRV-USD_PERP', 'FTM-USD_PERP', 'BCH-USD_PERP',
    #                'ADA-USD_PERP', 'CKB-USD_PERP', 'LINA-USD_PERP', 'IOTA-USD_PERP', 'LSK-USD_PERP', 'PHBT-USD_PERP', 'ATOM-USD_PERP',
    #                'LINK-USD_PERP', 'PHB-BTC_PERP', 'JOE-USD_PERP', 'DOT-USD_PERP', 'AVAX-USD_PERP', 'RAY-USD_PERP', 'ETC-USD_PERP', 'ALGO-USD_PERP',
    #                'FTT-USD_PERP', 'HNT-USD_PERP', 'DYDX-USD_PERP', 'WOO-USD_PERP', 'MANA-USD_PERP', 'SAND-USD_PERP', 'GALA-USD_PERP', 'DOGE-USD_PERP',
    #                'AAVE-USD_PERP', 'BNB-USD_PERP', 'KDA-USD_PERP', 'IMX-USD_PERP']

    # market_type = 'spot'
    market_type = 'future_u'
    # market_type = 'future_coin'
    update = exchange_info_update()
    data = update.update_info(exchange_name_list=exchange_name_list, symbol_list=symbol_list, market_type=market_type)

