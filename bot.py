import os
import discord
from discord.ext import commands
import anthropic
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

DISCORD_TOKEN = os.environ.get(‘DISCORD_TOKEN’)
ANTHROPIC_KEY = os.environ.get(‘ANTHROPIC_KEY’)

WATCHLIST = [
‘SPY’,‘QQQ’,‘NVDA’,‘AAPL’,‘MSFT’,‘TSLA’,‘AMZN’,‘META’,‘GOOGL’,‘AMD’,
‘XLE’,‘GLD’,‘WTI’,‘SLB’,‘EOG’,‘XOM’
]

WIZARD = ‘’’You are the Market Wizard. Elite institutional analyst. Smart money doctrine only. Every output is precise and deploy-ready.

DOCTRINE v4.0 - execute every layer in exact order:

L0 ENVIRONMENT: VIX<15=full size. VIX 15-25=reduced. VIX>25=minimal/cash. DXY up=risk off. Yields rising fast=equity headwind. Major calendar event in 24H=reduce size. Set macro bias: bullish/neutral/bearish.

L1 INSTITUTIONAL CYCLE: Accumulation=quiet low volume tight range smart money loading. Sweep=engineered stop hunt liquidity grab. Expansion=real move high volume directional. Distribution=topping action volume drying. Has sweep happened? Has MSS confirmed? No sweep + no MSS = wait.

L2 LIQUIDITY MAPPING: Mark every pool. Equal highs=buy stops above. Equal lows=sell stops below. Prev day H/L=most watched. Range H/L=compression targets. Prior swing H/L=major pools. Round numbers=psychological magnets. Key question: which pool is price drawn to next?

L3 ORDER BLOCK: Last bearish candle before displacement move up. Did displacement break structure? Yes=valid. Did it leave FVG? Yes=Tier1 OB. Mark zone top to bottom. This is stop anchor. Price must hold above it.

L4 FVG: Candle1 HIGH to Candle3 LOW = bullish FVG zone. Mark Top/50pct EQ/Bottom. Default entry=50pct EQ. Stop=below OB. Never enter FVG without confirmed MSS above it.

L5 PATTERNS: Tier1(+2pts): Bull Flag, Cup and Handle, Ascending Triangle, Double Bottom, Bull Pennant. Tier2(+1pt): Falling Wedge, Inverse H&S, Bullish Engulfing, Morning Star, Rounding Bottom. Tier3(+0): Three White Soldiers, Hammer, Rising Channel, Golden Cross. Structure+Pattern=maximum conviction. Pattern alone=weak. Never trade pattern against institutional cycle.

L6 MTF SCORE: Monthly/Weekly/Daily/4H/1H. 5/5=full size. 4/5=standard. 3/5=reduced. Less than 3=no trade.

L7 ENTRY CHECKLIST all 6 required for SNIPE IT: 1-Liquidity sweep confirmed below prior low. 2-MSS confirmed higher high made. 3-Price retracing into FVG zone. 4-Price at 50pct EQ of FVG. 5-Volume contracting on retracement. 6-Confirmation candle forming at FVG. All 6=SNIPE IT. Missing any=WAIT FOR ENTRY.

L8 TARGETS mark all before entry: T1=nearest opposing liquidity pool. T2=next major pool above T1. Runner=distant untouched pool. Minimum RR=3:1. Below 3:1=decline the trade always.

L9 RISK: Size=(Account x 1-2%) divided by (Entry price minus OB stop price). VIX>20=cut size 50pct. Never average down. Never remove stop once set.

4 DEMAND ELEMENTS all4=enter, 3=reduced, less than 3=noise: 1-Displacement large impulsive move. 2-Liquidity sweep of stops. 3-FVG imbalance left behind. 4-MSS structure break confirmed.

BREAKER BLOCK: Prior bearish OB that price has violated with bullish move. Old resistance=new support. Old shorts covering plus new longs entering=double demand. Retest of breaker=Tier A entry. No hesitation.

CONFLUENCE SCORING max 10: +2 Tier1 pattern clean and complete. +1 each: sweep confirmed, MSS confirmed, FVG 50pct holding, OB valid, MTF 3/5 or better, volume expansion on displacement, volume contraction on retracement, EMA stack 20>50>200.

OPTIONS: Early expansion strong momentum=high delta calls 0.70-0.85D 30-45DTE. Confirmed breakout live=slightly ITM call or 90DTE debit spread. Breaker block retest=ATM call 45DTE highest conviction. Late stage pressing resistance=STAND DOWN zero size always.

ENERGY SECTOR ADDONS for XLE,XOM,EOG,SLB,WTI: Also consider crude oil direction, OPEC headlines, DXY impact on commodities, seasonal demand cycles, rig count trends. WTI crude above 80=bullish energy. Below 70=bearish energy macro.

GOLD ADDON for GLD: DXY inverse relationship. Real yields direction. Fed policy bias. Safe haven flows. Central bank buying trends. GLD above 200EMA with falling real yields=maximum bullish.

OUTPUT FORMAT use exactly:
WIZARD [TICKER] [DATE TIME]
L0: VIX[x] Size:[full/reduced/minimal] Bias:[bull/neutral/bear] EventRisk:[y/n]
L1: Phase:[Accumulation/Sweep/Expansion/Distribution] Sweep:[y/n] MSS:[y/n]
L2: DrawnTo:$[x] reason:[x] PoolAbove:$[x] PoolBelow:$[x]
L3: OB $[lo]-$[hi] Valid:[y/n] reason:[x]
L4: FVG $[bot]-$[eq]-$[top] Entry:$[x] Stop:$[x]
L5: [Pattern] T[1/2/3] [Confirmed/Forming/Absent] Breaker:[y/n]
L6: M[y/n]W[y/n]D[y/n]4H[y/n]1H[y/n] Score:[x]/5
L7: Confirmed:[list] Missing:[list] Tier:[A/B/C] Entry:$[x] Invalid:$[x]
L8: T1:$[x] T2:$[x] Runner:$[x] RR:[x]:1
L9: Size=(Acct x 1pct)/[x] VIXadj:[y/n]
OPTIONS: $[strike] [expiry] [type] [rationale]
CONFLUENCE: [X/10]
VERDICT: [SNIPE IT / WAIT FOR ENTRY / PATTERN FORMING / STAND DOWN]
EDGE: [one sentence - single highest conviction reason to act or not act]

Score below 7: MONITORING [TICKER] - [reason] - revisit at $[level]

HARD LAWS never break: R1-SNIPE IT only when ALL 6 Layer7 confirmed. R2-No options without named invalidation price. R3-RR below 3:1=decline no exceptions ever. R4-VIX above 25=no full size. R5-Fewer than 3 demand elements=retail noise ignore. R6-MTF below 3/5=maximum verdict is WAIT never SNIPE IT. R7-Distribution phase=no entries wait for new accumulation.

THE FINAL PRINCIPLE: Retail asks which direction. Institutions ask where is the liquidity. Mark the pools. Wait for the sweep. Confirm the MSS. Enter the FVG. Target the opposing pool. Environment.Cycle.Liquidity.Structure.OB.FVG.MSS.Entry.Target. That order. Every time. No exceptions.’’’

def fetch(ticker):
try:
df = yf.download(ticker, period=‘6mo’, interval=‘1d’, progress=False, auto_adjust=True)
if df.empty: return {}
c = df[‘Close’].squeeze()
h = df[‘High’].squeeze()
l = df[‘Low’].squeeze()
v = df[‘Volume’].squeeze()
o = df[‘Open’].squeeze()
e20  = c.ewm(span=20,  adjust=False).mean()
e50  = c.ewm(span=50,  adjust=False).mean()
e200 = c.ewm(span=200, adjust=False).mean()
d    = c.diff()
rsi  = 100-(100/(1+d.clip(lower=0).rolling(14).mean()/(-d.clip(upper=0)).rolling(14).mean().replace(0,np.nan)))
tr   = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
atr  = tr.rolling(14).mean().iloc[-1]
vol_r = float(v.iloc[-1]/v.rolling(20).mean().iloc[-1])
cur  = float(c.iloc[-1])
sh   = float(h.tail(60).max())
sl   = float(l.tail(60).min())
fr   = sh - sl
h52  = float(h.tail(252).max())
l52  = float(l.tail(252).min())
fvg  = next(({‘top’:round(float(l.values[i+2]),2),‘eq’:round((float(l.values[i+2])+float(h.values[i]))/2,2),‘bot’:round(float(h.values[i]),2)} for i in range(len(df)-20,len(df)-2) if l.values[i+2]>h.values[i]),None)
ob   = next(({‘hi’:round(float(o.values[i]),2),‘lo’:round(float(c.values[i]),2)} for i in range(len(df)-20,len(df)-3) if c.values[i]<o.values[i] and c.values[i+1]>o.values[i+1]*1.005),None)
rl   = float(l.tail(10).min())
pl   = float(l.tail(20).min())
sweep = rl < pl*0.998
rh   = float(h.tail(5).max())
ph   = float(h.tail(20).iloc[:-5].max())
mss  = sweep and rh > ph
return dict(
ticker=ticker, cur=round(cur,2), h52=round(h52,2), l52=round(l52,2),
h20=round(float(h.tail(20).max()),2), l20=round(float(l.tail(20).min()),2),
e20=round(float(e20.iloc[-1]),2), e50=round(float(e50.iloc[-1]),2), e200=round(float(e200.iloc[-1]),2),
rsi=round(float(rsi.iloc[-1]),1), vol_r=round(vol_r,2), atr=round(float(atr),2),
bull=float(e20.iloc[-1])>float(e50.iloc[-1])>float(e200.iloc[-1]),
cons=bool(tr.rolling(5).mean().iloc[-1]<tr.rolling(20).mean().iloc[-1]*0.75),
f382=round(sh-fr*0.382,2), f618=round(sh-fr*0.618,2),
e1618=round(sh+fr*0.618,2), e2618=round(sh+fr*1.618,2),
sh=round(sh,2), sl=round(sl,2), fvg=fvg, ob=ob, sweep=sweep, mss=mss,
eqhi=round(float(h.tail(10).max()),2), eqlo=round(float(l.tail(10).min()),2),
pct=round((cur-h52)/h52*100,1),
ohlcv=df.tail(10)[[‘Open’,‘High’,‘Low’,‘Close’,‘Volume’]].round(2).to_string()
)
except Exception as e:
return {‘error’: str(e)}

def build_prompt(d):
fvg = ‘FVG Top $’+str(d[‘fvg’][‘top’])+’ EQ $’+str(d[‘fvg’][‘eq’])+’ Bot $’+str(d[‘fvg’][‘bot’]) if d.get(‘fvg’) else ‘No FVG detected’
ob  = ‘OB $’+str(d[‘ob’][‘lo’])+’-$’+str(d[‘ob’][‘hi’]) if d.get(‘ob’) else ‘No OB detected’
return (
‘LIVE INSTITUTIONAL DATA - ‘+d[‘ticker’]+’ - ‘+datetime.now().strftime(’%Y-%m-%d %H:%M ET’)+’\n’
‘Price: $’+str(d[‘cur’])+’ | 52W: $’+str(d[‘h52’])+’/$’+str(d[‘l52’])+’ (’+str(d[‘pct’])+’% from high)\n’
‘20D Range: $’+str(d[‘h20’])+’/$’+str(d[‘l20’])+’\n’
‘EMA: 20=$’+str(d[‘e20’])+’ 50=$’+str(d[‘e50’])+’ 200=$’+str(d[‘e200’])+’ Stack: ‘+(‘BULL 20>50>200’ if d[‘bull’] else ‘BEAR misaligned’)+’\n’
‘RSI: ‘+str(d[‘rsi’])+’ | Vol: ‘+str(d[‘vol_r’])+‘x avg | ATR: $’+str(d[‘atr’])+’ | Consolidating: ‘+(‘YES’ if d[‘cons’] else ‘NO’)+’\n’
‘Sweep: ‘+(‘YES’ if d[‘sweep’] else ‘NO’)+’ | MSS: ‘+(‘YES’ if d[‘mss’] else ‘NO’)+’\n’
+fvg+’\n’+ob+’\n’
‘Equal Highs: $’+str(d[‘eqhi’])+’ | Equal Lows: $’+str(d[‘eqlo’])+’\n’
‘Fibonacci: 0.382=$’+str(d[‘f382’])+’ | 0.618=$’+str(d[‘f618’])+’ | 1.618=$’+str(d[‘e1618’])+’ | 2.618=$’+str(d[‘e2618’])+’\n’
‘Swing: High $’+str(d[‘sh’])+’ Low $’+str(d[‘sl’])+’\n’
‘Recent OHLCV:\n’+d[‘ohlcv’]+’\n’
’Run full Doctrine v4.0 all layers in order. Score confluence 1-10. ’
’Score 7 or above=full 9-layer analysis. Score below 7=MONITORING note only. ’
‘Minimum 3:1 RR or decline. Include specific options play with strike and expiry.’
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=’!’, intents=intents, help_command=None)
ai  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def wizard(ticker):
d = fetch(ticker.upper())
if not d or ‘error’ in d:
return ‘Cannot fetch data for ‘+ticker+’. Check the ticker symbol.’
r = ai.messages.create(
model=‘claude-sonnet-4-6’,
max_tokens=1800,
system=WIZARD,
messages=[{‘role’:‘user’,‘content’:build_prompt(d)}]
)
return r.content[0].text

@bot.event
async def on_ready():
print(’Market Wizard LIVE - ’+str(bot.user))
print(’Watching: ‘+’, ’.join(WATCHLIST))

@bot.command(name=‘analyze’)
async def analyze(ctx, ticker: str = None):
if not ticker:
await ctx.send(‘Usage: !analyze NVDA’)
return
msg = await ctx.send(‘Running full doctrine on ‘+ticker.upper()+’…’)
try:
result = wizard(ticker)
chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
await msg.edit(content=chunks[0])
for chunk in chunks[1:]:
await ctx.send(chunk)
except Exception as e:
await msg.edit(content=’Error: ’+str(e))

@bot.command(name=‘scan’)
async def scan(ctx):
await ctx.send(‘Scanning ‘+str(len(WATCHLIST))+’ tickers - doctrine active…’)
snipes, waiting, forming = [], [], []
for t in WATCHLIST:
try:
a = wizard(t)
v = ‘’
score = 0
for line in a.split(’\n’):
if ‘VERDICT:’ in line:
v = line.split(‘VERDICT:’)[-1].strip()
if ‘CONFLUENCE:’ in line:
try:
score = int(line.split(‘CONFLUENCE:’)[-1].strip().split(’/’)[0].strip())
except:
pass
if ‘SNIPE IT’ in v:
snipes.append(t+’[’+str(score)+’]’)
await ctx.send(‘SNIPE IT - ‘+t+’\n’+a[:1800])
elif ‘WAIT’ in v:
waiting.append(t+’[’+str(score)+’]’)
elif ‘FORMING’ in v:
forming.append(t)
except:
pass
s = ‘WIZARD SCAN - ‘+datetime.now().strftime(’%H:%M ET’)+’\n’
if snipes:  s += ‘SNIPE IT: ‘+’ | ‘.join(snipes)+’\n’
if waiting: s += ‘WAIT: ‘+’ | ‘.join(waiting)+’\n’
if forming: s += ‘FORMING: ‘+’ | ‘.join(forming)+’\n’
if not snipes and not waiting:
s += ‘No high-conviction setups. Patience is the strategy.\n’
await ctx.send(s)

@bot.command(name=‘energy’)
async def energy(ctx):
await ctx.send(‘Scanning energy sector…’)
for t in [‘XLE’,‘XOM’,‘EOG’,‘SLB’,‘WTI’]:
try:
result = wizard(t)
await ctx.send(result[:1900])
except Exception as e:
await ctx.send(’Error on ‘+t+’: ’+str(e))

@bot.command(name=‘help’)
async def help_cmd(ctx):
await ctx.send(
‘MARKET WIZARD - COMMANDS\n’
‘!analyze [TICKER] - Full 10-layer institutional doctrine\n’
‘!scan - Scan all ‘+str(len(WATCHLIST))+’ tickers for SNIPE IT signals\n’
‘!energy - Deep scan energy sector XLE XOM EOG SLB WTI\n’
‘!help - This menu\n’
‘Watchlist: ‘+’, ‘.join(WATCHLIST)+’\n’
‘Min 3:1 RR always. SNIPE IT = all 6 Layer7 confirmed.\n’
‘The law: Mark the pools. Wait for the sweep. Confirm the MSS. Enter the FVG.’
)

bot.run(DISCORD_TOKEN)