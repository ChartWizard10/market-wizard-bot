import os 
import discord
from discord.ext import commands
import anthropic
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
WATCHLIST = [“SPY”,“QQQ”,“NVDA”,“AAPL”,“XLE”,“TSLA”,“SLB”,“META”,“GOOGL”,“AMD”]

WIZARD = “”“You are the Market Wizard — elite institutional analyst. Smart money doctrine only. Every output is precise and deploy-ready.

DOCTRINE v4.0 — run every layer in order:

L0 ENVIRONMENT: VIX<15=full|15-25=reduced|>25=minimal. DXY,yields,calendar,macro bias.
L1 CYCLE: Accumulation/Sweep/Expansion/Distribution. Sweep confirmed? MSS confirmed? No sweep+MSS=wait.
L2 LIQUIDITY: Map equal highs/lows, prev day H/L, range H/L, swing H/L, round numbers. Key Q: Which pool is price drawn to next?
L3 ORDER BLOCK: Last bearish candle before displacement. Structure break+FVG=Tier 1 OB. Mark zone. Stop anchor.
L4 FVG: Candle1 HIGH to Candle3 LOW=zone. Top/50%EQ/Bottom. Default entry=50%EQ. Stop=below OB. No FVG entry without MSS.
L5 PATTERNS: T1(+2): Bull Flag,Cup&Handle,Asc Triangle,Dbl Bottom,Bull Pennant. T2(+1): Falling Wedge,InvH&S,Engulfing,Morning Star. Structure+Pattern=max conviction. Pattern alone=weak.
L6 MTF: Monthly/Weekly/Daily/4H/1H. 5/5=full|4/5=standard|3/5=reduced|<3=no trade.
L7 ENTRY (all 6 = SNIPE IT): Sweep confirmed. MSS confirmed. Retracing into FVG. At 50%EQ. Volume contracting. Confirm candle forming.
L8 TARGETS: T1=nearest pool. T2=next pool. Runner=distant pool. All marked before entry. Min 3:1 R:R or decline.
L9 RISK: Size=(Acct x 1-2%) divided by (entry minus OB stop). VIX>20=cut 50%. Never move stop.

4 DEMAND ELEMENTS (all4=enter|3=reduced|<3=noise): Displacement + Liquidity Sweep + FVG Imbalance + MSS

BREAKER BLOCK: Prior bearish OB violated by bull move = polarity flip. Old resistance=new support. Double demand. Tier A entry on retest.

CONFLUENCE (max 10): +2 T1 pattern | +1 each: sweep,MSS,FVG holding,OB valid,MTF>=3/5,vol expansion,vol contraction,EMA stack 20>50>200

OPTIONS: Early expansion=high delta calls 0.70-0.85D 30-45DTE | Confirmed breakout=ITM call or 90DTE spread | Breaker retest=ATM 45DTE | Late stage=STAND DOWN

OUTPUT FORMAT:
WIZARD [TICKER] [TIME]
L0: VIX[x] Size:[x] Bias:[x] Risk:[y/n]
L1: Phase:[x] Sweep:[y/n] MSS:[y/n]
L2: Drawn to $[x] reason:[x] Above:$[x] Below:$[x]
L3: OB $[lo]-$[hi] Valid:[y/n]
L4: FVG $[bot]-$[eq]-$[top] Entry:$[x] Stop:$[x]
L5: [Pattern] T[1/2/3] [status] Breaker:[y/n]
L6: M[y/n]W[y/n]D[y/n]4H[y/n]1H[y/n] Score:[x]/5
L7: Checklist:[list confirmed] Tier:[A/B/C] Entry:$[x] Invalid:$[x]
L8: T1:$[x] T2:$[x] Runner:$[x] RR:[x]:1
L9: Size=(Acct x 1%) / $[x] VIX adj:[y/n]
OPTIONS: $[strike] [exp] [type] [rationale]
CONFLUENCE: [X/10]
VERDICT: [SNIPE IT / WAIT FOR ENTRY / PATTERN FORMING / STAND DOWN]
EDGE: [one sentence highest conviction reason]

Score<7: MONITORING [TICKER] reason revisit $[x]

LAWS: SNIPE IT only all 6 L7 confirmed. No options without invalidation. RR<3:1=decline always. VIX>25=no full size. <3 demand elements=ignore. MTF<3/5=max WAIT. Distribution=no entries.

THE LAW: Environment.Cycle.Liquidity.Structure.OB.FVG.MSS.Entry.Target. That order. Every time. No exceptions. This is reading institutional intent.”””

def fetch(ticker):
try:
df = yf.download(ticker, period=“6mo”, interval=“1d”, progress=False, auto_adjust=True)
if df.empty: return {}
c,h,l,v,o = df[“Close”].squeeze(),df[“High”].squeeze(),df[“Low”].squeeze(),df[“Volume”].squeeze(),df[“Open”].squeeze()
e20=c.ewm(span=20,adjust=False).mean()
e50=c.ewm(span=50,adjust=False).mean()
e200=c.ewm(span=200,adjust=False).mean()
d=c.diff()
rsi=100-(100/(1+d.clip(lower=0).rolling(14).mean()/(-d.clip(upper=0)).rolling(14).mean().replace(0,np.nan)))
tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
atr=tr.rolling(14).mean().iloc[-1]
vol_r=float(v.iloc[-1]/v.rolling(20).mean().iloc[-1])
cur=float(c.iloc[-1])
sh=float(h.tail(60).max()); sl=float(l.tail(60).min()); fr=sh-sl
fvg=next(({‘top’:round(float(l.values[i+2]),2),‘eq’:round((float(l.values[i+2])+float(h.values[i]))/2,2),‘bot’:round(float(h.values[i]),2)} for i in range(len(df)-20,len(df)-2) if l.values[i+2]>h.values[i]),None)
ob=next(({‘hi’:round(float(o.values[i]),2),‘lo’:round(float(c.values[i]),2)} for i in range(len(df)-20,len(df)-3) if c.values[i]<o.values[i] and c.values[i+1]>o.values[i+1]*1.005),None)
rl=float(l.tail(10).min()); pl=float(l.tail(20).min()); sweep=rl<pl*0.998
rh=float(h.tail(5).max()); ph=float(h.tail(20).iloc[:-5].max()); mss=sweep and rh>ph
h52=float(h.tail(252).max())
return dict(ticker=ticker,cur=round(cur,2),h52=round(h52,2),l52=round(float(l.tail(252).min()),2),
h20=round(float(h.tail(20).max()),2),l20=round(float(l.tail(20).min()),2),
e20=round(float(e20.iloc[-1]),2),e50=round(float(e50.iloc[-1]),2),e200=round(float(e200.iloc[-1]),2),
rsi=round(float(rsi.iloc[-1]),1),vol_r=round(vol_r,2),atr=round(float(atr),2),
bull=float(e20.iloc[-1])>float(e50.iloc[-1])>float(e200.iloc[-1]),
cons=bool(tr.rolling(5).mean().iloc[-1]<tr.rolling(20).mean().iloc[-1]*0.75),
f382=round(sh-fr*0.382,2),f618=round(sh-fr*0.618,2),
e1618=round(sh+fr*0.618,2),e2618=round(sh+fr*1.618,2),
sh=round(sh,2),sl=round(sl,2),fvg=fvg,ob=ob,sweep=sweep,mss=mss,
eqhi=round(float(h.tail(10).max()),2),eqlo=round(float(l.tail(10).min()),2),
pct=round((cur-h52)/h52*100,1),
ohlcv=df.tail(10)[[“Open”,“High”,“Low”,“Close”,“Volume”]].round(2).to_string())
except Exception as e:
return {“error”:str(e)}

def build_prompt(d):
fvg = f”FVG: Top${d[‘fvg’][‘top’]} EQ${d[‘fvg’][‘eq’]} Bot${d[‘fvg’][‘bot’]}” if d.get(‘fvg’) else “No FVG detected”
ob  = f”OB: ${d[‘ob’][‘lo’]}-${d[‘ob’][‘hi’]}” if d.get(‘ob’) else “No OB detected”
return f””“LIVE DATA {d[‘ticker’]} {datetime.now().strftime(’%Y-%m-%d %H:%M ET’)}
Price:${d[‘cur’]} 52W:${d[‘h52’]}/${d[‘l52’]}({d[‘pct’]}%) 20D:${d[‘h20’]}/${d[‘l20’]}
EMA: 20=${d[‘e20’]} 50=${d[‘e50’]} 200=${d[‘e200’]} Stack:{‘BULL’ if d[‘bull’] else ‘BEAR’}
RSI:{d[‘rsi’]} Vol:{d[‘vol_r’]}x ATR:${d[‘atr’]} Cons:{‘YES’ if d[‘cons’] else ‘NO’}
Sweep:{‘YES’ if d[‘sweep’] else ‘NO’} MSS:{‘YES’ if d[‘mss’] else ‘NO’} {fvg} {ob}
EqHi:${d[‘eqhi’]} EqLo:${d[‘eqlo’]} Fib:0.382=${d[‘f382’]} 0.618=${d[‘f618’]} 1.618=${d[‘e1618’]}
OHLCV:
{d[‘ohlcv’]}
Run full doctrine v4.0 all layers. Score 1-10. >=7=full analysis. <7=MONITORING. Min 3:1 RR.”””

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=”!”, intents=intents, help_command=None)
ai  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def wizard(ticker):
d = fetch(ticker.upper())
if not d or “error” in d: return f”Cannot fetch {ticker}”
r = ai.messages.create(model=“claude-sonnet-4-6”,max_tokens=1800,system=WIZARD,
messages=[{“role”:“user”,“content”:build_prompt(d)}])
return r.content[0].text

@bot.event
async def on_ready():
print(f”Market Wizard LIVE {bot.user}”)

@bot.command(name=“analyze”)
async def analyze(ctx, ticker: str = None):
if not ticker:
await ctx.send(“Usage: !analyze NVDA”); return
msg = await ctx.send(f”Running doctrine on {ticker.upper()}…”)
try:
result = wizard(ticker)
chunks = [result[i:i+1900] for i in range(0,len(result),1900)]
await msg.edit(content=chunks[0])
for chunk in chunks[1:]: await ctx.send(chunk)
except Exception as e:
await msg.edit(content=f”Error: {e}”)

@bot.command(name=“scan”)
async def scan(ctx):
await ctx.send(f”Scanning {len(WATCHLIST)} tickers…”)
snipes,waiting,forming=[],[],[]
for t in WATCHLIST:
try:
a=wizard(t); v=””; score=0
for line in a.split(”\n”):
if “VERDICT:” in line: v=line.split(“VERDICT:”)[-1].strip()
if “CONFLUENCE:” in line:
try: score=int(line.split(“CONFLUENCE:”)[-1].strip().split(”/”)[0].strip())
except: pass
if “SNIPE IT” in v: snipes.append(f”{t}[{score}]”); await ctx.send(f”SNIPE {t}\n{a[:1800]}”)
elif “WAIT” in v: waiting.append(f”{t}[{score}]”)
elif “FORMING” in v: forming.append(t)
except: pass
s=f”SCAN {datetime.now().strftime(’%H:%M ET’)}\n”
if snipes: s+=f”SNIPE IT: {’ ‘.join(snipes)}\n”
if waiting: s+=f”WAIT: {’ ‘.join(waiting)}\n”
if forming: s+=f”FORMING: {’ ’.join(forming)}\n”
if not snipes and not waiting: s+=“No setups. Patience is the strategy.”
await ctx.send(s)

@bot.command(name=“help”)
async def help_cmd(ctx):
await ctx.send(“MARKET WIZARD\n!analyze [TICKER] — full doctrine\n!scan — scan watchlist\n!help — this menu\nMin 3:1 RR. SNIPE IT = all 6 Layer 7 confirmed.”)

bot.run(DISCORD_TOKEN)
