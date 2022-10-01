import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import mplfinance as mpf
import matplotlib.ticker as ticker
# 图表显示中文用---------------------------
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
np.seterr(divide='ignore', invalid='ignore')    # 忽略warning
plt.rcParams['font.sans-serif'] = ['SimHei']    # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False      # 用来正常显示负号
plt.rcParams['figure.figsize'] = (16, 8)
'''
    该文件用于展示交易信号和K线图
'''
# 设定品种
exchange_name = 'binance'
symbol = 'BNB-USDT'
# 使用什么数据
market_type = 'spot'
# 设置回测时间周期
time_period = '1hour'
# 设置回测时间
test_time = ['2022/01/01 08:00:00', '2022/03/22 08:00:00']


file = pd.read_csv(
    f"D:\\quant\\data_history\\DIGICCY_data\\{exchange_name}_data\\{market_type}_data\\{symbol}\\{symbol}({time_period}).csv",
    names=['datetime', 'open', 'high', 'low', 'close', 'volume'])
# 创建表格
df = pd.DataFrame(file)

# 根据回测时间，筛选数据
s = pd.to_datetime(test_time[0])
e = pd.to_datetime(test_time[1])
df['datetime'] = pd.to_datetime(df['datetime'])
df = df.loc[(df.datetime >= s) & (df.datetime <= e)]
# 重置索引
df = df.reset_index()
df.drop(['index'], axis=1, inplace=True)


# 处理日期
df['datetime'] = pd.to_datetime(df['datetime'])
df.set_index("datetime", inplace=True)

fig, ax, = plt.subplots()

ax.set_zorder(1)
ax.set_frame_on(False)

# 设置K线的颜色
mc = mpf.make_marketcolors(up='red', down='green', edge='i', wick='i', inherit=False)
s = mpf.make_mpf_style(marketcolors=mc)

# 设置显示长度
plotlen = len(df)


# 横坐标为日期
def mydate_formatter(x, pos):
    try:
        return df.iloc[int(x)]['datetime']
    except IndexError:
        return ''


ax.xaxis.set_major_formatter(ticker.FuncFormatter(mydate_formatter))
# 自动旋转X轴
fig.autofmt_xdate()
# 设置成交量显示
ax2 = ax.twinx()
ax2.grid(False)
# 关闭坐标轴
plt.axis('off')
plt.title(f"{symbol}({exchange_name})", fontsize=24)
mpf.plot(df, ax=ax, type='candle', warn_too_much_data=plotlen, mav=(20, 60), style=s, volume=ax2)

plt.show()


