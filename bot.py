import os
import base64
import discord
from discord.ext import commands
import anthropic
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

    WATCHLIST = ["SPY","QQQ","NVDA","AAPL","MSFT","TSLA","AMZN","META","GOOGL","AMD","XLE","GLD","WTI","SLB","EOG","XOM"]

WIZARD = base64.b64decode("WW91IGFyZSB0aGUgTWFya2V0IFdpemFyZC4gRWxpdGUgaW5zdGl0dXRpb25hbCBhbmFseXN0LiBTbWFydCBtb25leSBkb2N0cmluZSBvbmx5LiBFdmVyeSBvdXRwdXQgaXMgcHJlY2lzZSBhbmQgZGVwbG95LXJlYWR5LgoKRE9DVFJJTkUgdjQuMCAtIGV4ZWN1dGUgZXZlcnkgbGF5ZXIgaW4gZXhhY3Qgb3JkZXI6CgpMMCBFTlZJUk9OTUVOVDogVklYPDE1PWZ1bGwgc2l6ZS4gVklYIDE1LTI1PXJlZHVjZWQuIFZJWD4yNT1taW5pbWFsL2Nhc2guIERYWSB1cD1yaXNrIG9mZi4gWWllbGRzIHJpc2luZyBmYXN0PWVxdWl0eSBoZWFkd2luZC4gTWFqb3IgY2FsZW5kYXIgZXZlbnQgaW4gMjRIPXJlZHVjZSBzaXplLiBTZXQgbWFjcm8gYmlhczogYnVsbGlzaC9uZXV0cmFsL2JlYXJpc2guCgpMMSBJTlNUSVRVVElPTkFMIENZQ0xFOiBBY2N1bXVsYXRpb249cXVpZXQgbG93IHZvbHVtZSB0aWdodCByYW5nZSBzbWFydCBtb25leSBsb2FkaW5nLiBTd2VlcD1lbmdpbmVlcmVkIHN0b3AgaHVudCBsaXF1aWRpdHkgZ3JhYi4gRXhwYW5zaW9uPXJlYWwgbW92ZSBoaWdoIHZvbHVtZSBkaXJlY3Rpb25hbC4gRGlzdHJpYnV0aW9uPXRvcHBpbmcgYWN0aW9uIHZvbHVtZSBkcnlpbmcuIEhhcyBzd2VlcCBoYXBwZW5lZD8gSGFzIE1TUyBjb25maXJtZWQ/IE5vIHN3ZWVwICsgbm8gTVNTID0gd2FpdC4KCkwyIExJUVVJRElUWSBNQVBQSU5HOiBNYXJrIGV2ZXJ5IHBvb2wuIEVxdWFsIGhpZ2hzPWJ1eSBzdG9wcyBhYm92ZS4gRXF1YWwgbG93cz1zZWxsIHN0b3BzIGJlbG93LiBQcmV2IGRheSBIL0w9bW9zdCB3YXRjaGVkLiBSYW5nZSBIL0w9Y29tcHJlc3Npb24gdGFyZ2V0cy4gUHJpb3Igc3dpbmcgSC9MPW1ham9yIHBvb2xzLiBSb3VuZCBudW1iZXJzPXBzeWNob2xvZ2ljYWwgbWFnbmV0cy4gS2V5IHF1ZXN0aW9uOiB3aGljaCBwb29sIGlzIHByaWNlIGRyYXduIHRvIG5leHQ/CgpMMyBPUkRFUiBCTE9DSzogTGFzdCBiZWFyaXNoIGNhbmRsZSBiZWZvcmUgZGlzcGxhY2VtZW50IG1vdmUgdXAuIERpZCBkaXNwbGFjZW1lbnQgYnJlYWsgc3RydWN0dXJlPyBZZXM9dmFsaWQuIERpZCBpdCBsZWF2ZSBGVkc/IFllcz1UaWVyMSBPQi4gTWFyayB6b25lIHRvcCB0byBib3R0b20uIFRoaXMgaXMgc3RvcCBhbmNob3IuIFByaWNlIG11c3QgaG9sZCBhYm92ZSBpdC4KCkw0IEZWRzogQ2FuZGxlMSBISUdIIHRvIENhbmRsZTMgTE9XID0gYnVsbGlzaCBGVkcgem9uZS4gTWFyayBUb3AvNTBwY3QgRVEvQm90dG9tLiBEZWZhdWx0IGVudHJ5PTUwcGN0IEVRLiBTdG9wPWJlbG93IE9CLiBOZXZlciBlbnRlciBGVkcgd2l0aG91dCBjb25maXJtZWQgTVNTIGFib3ZlIGl0LgoKTDUgUEFUVEVSTlM6IFRpZXIxKCsycHRzKTogQnVsbCBGbGFnLCBDdXAgYW5kIEhhbmRsZSwgQXNjZW5kaW5nIFRyaWFuZ2xlLCBEb3VibGUgQm90dG9tLCBCdWxsIFBlbm5hbnQuIFRpZXIyKCsxcHQpOiBGYWxsaW5nIFdlZGdlLCBJbnZlcnNlIEgmUywgQnVsbGlzaCBFbmd1bGZpbmcsIE1vcm5pbmcgU3RhciwgUm91bmRpbmcgQm90dG9tLiBUaWVyMzogVGhyZWUgV2hpdGUgU29sZGllcnMsIEhhbW1lciwgUmlzaW5nIENoYW5uZWwsIEdvbGRlbiBDcm9zcy4gU3RydWN0dXJlK1BhdHRlcm49bWF4aW11bSBjb252aWN0aW9uLiBQYXR0ZXJuIGFsb25lPXdlYWsuIE5ldmVyIHRyYWRlIHBhdHRlcm4gYWdhaW5zdCBpbnN0aXR1dGlvbmFsIGN5Y2xlLgoKTDYgTVRGIFNDT1JFOiBNb250aGx5L1dlZWtseS9EYWlseS80SC8xSC4gNS81PWZ1bGwgc2l6ZS4gNC81PXN0YW5kYXJkLiAzLzU9cmVkdWNlZC4gTGVzcyB0aGFuIDM9bm8gdHJhZGUuCgpMNyBFTlRSWSBDSEVDS0xJU1QgYWxsIDYgcmVxdWlyZWQgZm9yIFNOSVBFIElUOiAxLUxpcXVpZGl0eSBzd2VlcCBjb25maXJtZWQgYmVsb3cgcHJpb3IgbG93LiAyLU1TUyBjb25maXJtZWQgaGlnaGVyIGhpZ2ggbWFkZS4gMy1QcmljZSByZXRyYWNpbmcgaW50byBGVkcgem9uZS4gNC1QcmljZSBhdCA1MHBjdCBFUSBvZiBGVkcuIDUtVm9sdW1lIGNvbnRyYWN0aW5nIG9uIHJldHJhY2VtZW50LiA2LUNvbmZpcm1hdGlvbiBjYW5kbGUgZm9ybWluZyBhdCBGVkcuIEFsbCA2PVNOSVBFIElULiBNaXNzaW5nIGFueT1XQUlUIEZPUiBFTlRSWS4KCkw4IFRBUkdFVFMgbWFyayBhbGwgYmVmb3JlIGVudHJ5OiBUMT1uZWFyZXN0IG9wcG9zaW5nIGxpcXVpZGl0eSBwb29sLiBUMj1uZXh0IG1ham9yIHBvb2wgYWJvdmUgVDEuIFJ1bm5lcj1kaXN0YW50IHVudG91Y2hlZCBwb29sLiBNaW5pbXVtIFJSPTM6MS4gQmVsb3cgMzoxPWRlY2xpbmUgdGhlIHRyYWRlIGFsd2F5cy4KCkw5IFJJU0s6IFNpemU9KEFjY291bnQgeCAxLTIlKSBkaXZpZGVkIGJ5IChFbnRyeSBwcmljZSBtaW51cyBPQiBzdG9wIHByaWNlKS4gVklYPjIwPWN1dCBzaXplIDUwcGN0LiBOZXZlciBhdmVyYWdlIGRvd24uIE5ldmVyIHJlbW92ZSBzdG9wIG9uY2Ugc2V0LgoKNCBERU1BTkQgRUxFTUVOVFMgYWxsND1lbnRlciwgMz1yZWR1Y2VkLCBsZXNzIHRoYW4gMz1ub2lzZTogMS1EaXNwbGFjZW1lbnQgbGFyZ2UgaW1wdWxzaXZlIG1vdmUuIDItTGlxdWlkaXR5IHN3ZWVwIG9mIHN0b3BzLiAzLUZWRyBpbWJhbGFuY2UgbGVmdCBiZWhpbmQuIDQtTVNTIHN0cnVjdHVyZSBicmVhayBjb25maXJtZWQuCgpCUkVBS0VSIEJMT0NLOiBQcmlvciBiZWFyaXNoIE9CIHRoYXQgcHJpY2UgaGFzIHZpb2xhdGVkIHdpdGggYnVsbGlzaCBtb3ZlLiBPbGQgcmVzaXN0YW5jZT1uZXcgc3VwcG9ydC4gT2xkIHNob3J0cyBjb3ZlcmluZyBwbHVzIG5ldyBsb25ncyBlbnRlcmluZz1kb3VibGUgZGVtYW5kLiBSZXRlc3Qgb2YgYnJlYWtlcj1UaWVyIEEgZW50cnkuIE5vIGhlc2l0YXRpb24uCgpDT05GTFVFTkNFIFNDT1JJTkcgbWF4IDEwOiArMiBUaWVyMSBwYXR0ZXJuIGNsZWFuIGFuZCBjb21wbGV0ZS4gKzEgZWFjaDogc3dlZXAgY29uZmlybWVkLCBNU1MgY29uZmlybWVkLCBGVkcgNTBwY3QgaG9sZGluZywgT0IgdmFsaWQsIE1URiAzLzUgb3IgYmV0dGVyLCB2b2x1bWUgZXhwYW5zaW9uIG9uIGRpc3BsYWNlbWVudCwgdm9sdW1lIGNvbnRyYWN0aW9uIG9uIHJldHJhY2VtZW50LCBFTUEgc3RhY2sgMjA+NTA+MjAwLgoKT1BUSU9OUzogRWFybHkgZXhwYW5zaW9uIHN0cm9uZyBtb21lbnR1bT1oaWdoIGRlbHRhIGNhbGxzIDAuNzAtMC44NUQgMzAtNDVEVEUuIENvbmZpcm1lZCBicmVha291dCBsaXZlPXNsaWdodGx5IElUTSBjYWxsIG9yIDkwRFRFIGRlYml0IHNwcmVhZC4gQnJlYWtlciBibG9jayByZXRlc3Q9QVRNIGNhbGwgNDVEVEUgaGlnaGVzdCBjb252aWN0aW9uLiBMYXRlIHN0YWdlIHByZXNzaW5nIHJlc2lzdGFuY2U9U1RBTkQgRE9XTiB6ZXJvIHNpemUgYWx3YXlzLgoKRU5FUkdZIFNFQ1RPUiBmb3IgWExFLFhPTSxFT0csU0xCLFdUSTogQ29uc2lkZXIgY3J1ZGUgb2lsIGRpcmVjdGlvbiwgT1BFQyBoZWFkbGluZXMsIERYWSBpbXBhY3Qgb24gY29tbW9kaXRpZXMsIHNlYXNvbmFsIGRlbWFuZCBjeWNsZXMsIHJpZyBjb3VudCB0cmVuZHMuIFdUSSBjcnVkZSBhYm92ZSA4MD1idWxsaXNoIGVuZXJneS4gQmVsb3cgNzA9YmVhcmlzaCBlbmVyZ3kgbWFjcm8uCgpHT0xEIGZvciBHTEQ6IERYWSBpbnZlcnNlIHJlbGF0aW9uc2hpcC4gUmVhbCB5aWVsZHMgZGlyZWN0aW9uLiBGZWQgcG9saWN5IGJpYXMuIFNhZmUgaGF2ZW4gZmxvd3MuIENlbnRyYWwgYmFuayBidXlpbmcgdHJlbmRzLiBHTEQgYWJvdmUgMjAwRU1BIHdpdGggZmFsbGluZyByZWFsIHlpZWxkcz1tYXhpbXVtIGJ1bGxpc2guCgpPVVRQVVQgRk9STUFUOgpXSVpBUkQgW1RJQ0tFUl0gW0RBVEUgVElNRV0KTDA6IFZJWFt4XSBTaXplOltmdWxsL3JlZHVjZWQvbWluaW1hbF0gQmlhczpbYnVsbC9uZXV0cmFsL2JlYXJdIEV2ZW50UmlzazpbeS9uXQpMMTogUGhhc2U6W3hdIFN3ZWVwOlt5L25dIE1TUzpbeS9uXQpMMjogRHJhd25UbzokW3hdIHJlYXNvbjpbeF0gUG9vbEFib3ZlOiRbeF0gUG9vbEJlbG93OiRbeF0KTDM6IE9CICRbbG9dLSRbaGldIFZhbGlkOlt5L25dCkw0OiBGVkcgJFtib3RdLSRbZXFdLSRbdG9wXSBFbnRyeTokW3hdIFN0b3A6JFt4XQpMNTogW1BhdHRlcm5dIFRbMS8yLzNdIFtDb25maXJtZWQvRm9ybWluZy9BYnNlbnRdIEJyZWFrZXI6W3kvbl0KTDY6IE1beS9uXVdbeS9uXURbeS9uXTRIW3kvbl0xSFt5L25dIFNjb3JlOlt4XS81Ckw3OiBDb25maXJtZWQ6W2xpc3RdIE1pc3Npbmc6W2xpc3RdIFRpZXI6W0EvQi9DXSBFbnRyeTokW3hdIEludmFsaWQ6JFt4XQpMODogVDE6JFt4XSBUMjokW3hdIFJ1bm5lcjokW3hdIFJSOlt4XToxCkw5OiBTaXplPShBY2N0IHggMXBjdCkvW3hdIFZJWGFkajpbeS9uXQpPUFRJT05TOiAkW3N0cmlrZV0gW2V4cGlyeV0gW3R5cGVdIFtyYXRpb25hbGVdCkNPTkZMVUVOQ0U6IFtYLzEwXQpWRVJESUNUOiBbU05JUEUgSVQgLyBXQUlUIEZPUiBFTlRSWSAvIFBBVFRFUk4gRk9STUlORyAvIFNUQU5EIERPV05dCkVER0U6IFtvbmUgc2VudGVuY2UgLSBzaW5nbGUgaGlnaGVzdCBjb252aWN0aW9uIHJlYXNvbl0KClNjb3JlIGJlbG93IDc6IE1PTklUT1JJTkcgW1RJQ0tFUl0gLSBbcmVhc29uXSAtIHJldmlzaXQgYXQgJFtsZXZlbF0KCkhBUkQgTEFXUzogUjEtU05JUEUgSVQgb25seSB3aGVuIEFMTCA2IExheWVyNyBjb25maXJtZWQuIFIyLU5vIG9wdGlvbnMgd2l0aG91dCBuYW1lZCBpbnZhbGlkYXRpb24uIFIzLVJSIGJlbG93IDM6MT1kZWNsaW5lIGFsd2F5cy4gUjQtVklYIGFib3ZlIDI1PW5vIGZ1bGwgc2l6ZS4gUjUtRmV3ZXIgdGhhbiAzIGRlbWFuZCBlbGVtZW50cz1pZ25vcmUuIFI2LU1URiBiZWxvdyAzLzU9bWF4aW11bSBXQUlUIG5ldmVyIFNOSVBFIElULiBSNy1EaXN0cmlidXRpb249bm8gZW50cmllcy4KClRIRSBMQVc6IE1hcmsgdGhlIHBvb2xzLiBXYWl0IGZvciB0aGUgc3dlZXAuIENvbmZpcm0gdGhlIE1TUy4gRW50ZXIgdGhlIEZWRy4gVGFyZ2V0IHRoZSBvcHBvc2luZyBwb29sLiBFbnZpcm9ubWVudC5DeWNsZS5MaXF1aWRpdHkuU3RydWN0dXJlLk9CLkZWRy5NU1MuRW50cnkuVGFyZ2V0LiBUaGF0IG9yZGVyLiBFdmVyeSB0aW1lLiBObyBleGNlcHRpb25zLg==”).decode()

def fetch(ticker):
try:
df = yf.download(ticker, period=“6mo”, interval=“1d”, progress=False, auto_adjust=True)
if df.empty: return {}
c=df[“Close”].squeeze(); h=df[“High”].squeeze(); l=df[“Low”].squeeze()
v=df[“Volume”].squeeze(); o=df[“Open”].squeeze()
e20=c.ewm(span=20,adjust=False).mean()
e50=c.ewm(span=50,adjust=False).mean()
e200=c.ewm(span=200,adjust=False).mean()
d=c.diff()
rsi=100-(100/(1+d.clip(lower=0).rolling(14).mean()/(-d.clip(upper=0)).rolling(14).mean().replace(0,np.nan)))
tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
atr=tr.rolling(14).mean().iloc[-1]
vol_r=float(v.iloc[-1]/v.rolling(20).mean().iloc[-1])
cur=float(c.iloc[-1]); sh=float(h.tail(60).max()); sl=float(l.tail(60).min()); fr=sh-sl
h52=float(h.tail(252).max()); l52=float(l.tail(252).min())
fvg=next(({“top”:round(float(l.values[i+2]),2),“eq”:round((float(l.values[i+2])+float(h.values[i]))/2,2),“bot”:round(float(h.values[i]),2)} for i in range(len(df)-20,len(df)-2) if l.values[i+2]>h.values[i]),None)
ob=next(({“hi”:round(float(o.values[i]),2),“lo”:round(float(c.values[i]),2)} for i in range(len(df)-20,len(df)-3) if c.values[i]<o.values[i] and c.values[i+1]>o.values[i+1]*1.005),None)
rl=float(l.tail(10).min()); pl=float(l.tail(20).min()); sweep=rl<pl*0.998
rh=float(h.tail(5).max()); ph=float(h.tail(20).iloc[:-5].max()); mss=sweep and rh>ph
return dict(ticker=ticker,cur=round(cur,2),h52=round(h52,2),l52=round(l52,2),
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
fvg=“FVG Top $”+str(d[“fvg”][“top”])+” EQ $”+str(d[“fvg”][“eq”])+” Bot $”+str(d[“fvg”][“bot”]) if d.get(“fvg”) else “No FVG”
ob=“OB $”+str(d[“ob”][“lo”])+”-$”+str(d[“ob”][“hi”]) if d.get(“ob”) else “No OB”
return (“LIVE DATA “+d[“ticker”]+” “+datetime.now().strftime(”%Y-%m-%d %H:%M ET”)+”\n”
“Price $”+str(d[“cur”])+” 52W $”+str(d[“h52”])+”/$”+str(d[“l52”])+” (”+str(d[“pct”])+”%)\n”
“EMA 20=$”+str(d[“e20”])+” 50=$”+str(d[“e50”])+” 200=$”+str(d[“e200”])+” Stack “+(“BULL” if d[“bull”] else “BEAR”)+”\n”
“RSI “+str(d[“rsi”])+” Vol “+str(d[“vol_r”])+“x ATR $”+str(d[“atr”])+” Cons “+(“YES” if d[“cons”] else “NO”)+”\n”
“Sweep “+(“YES” if d[“sweep”] else “NO”)+” MSS “+(“YES” if d[“mss”] else “NO”)+”\n”
+fvg+”\n”+ob+”\n”
“EqHi $”+str(d[“eqhi”])+” EqLo $”+str(d[“eqlo”])+”\n”
“Fib 0.382=$”+str(d[“f382”])+” 0.618=$”+str(d[“f618”])+” 1.618=$”+str(d[“e1618”])+”\n”
“Swing Hi $”+str(d[“sh”])+” Lo $”+str(d[“sl”])+”\n”
“OHLCV:\n”+d[“ohlcv”]+”\n”
“Run full Doctrine v4.0 all layers. Score 1-10. 7+=full analysis. <7=MONITORING. Min 3:1 RR.”)

intents=discord.Intents.default()
intents.message_content=True
bot=commands.Bot(command_prefix=”!”,intents=intents,help_command=None)
ai=anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def wizard(ticker):
d=fetch(ticker.upper())
if not d or “error” in d: return “Cannot fetch “+ticker
r=ai.messages.create(model=“claude-sonnet-4-6”,max_tokens=1800,system=WIZARD,
messages=[{“role”:“user”,“content”:build_prompt(d)}])
return r.content[0].text

@bot.event
async def on_ready():
print(“Market Wizard LIVE “+str(bot.user))

@bot.command(name=“analyze”)
async def analyze(ctx,ticker:str=None):
if not ticker:
await ctx.send(“Usage: !analyze NVDA”); return
msg=await ctx.send(“Running doctrine on “+ticker.upper()+”…”)
try:
result=wizard(ticker)
chunks=[result[i:i+1900] for i in range(0,len(result),1900)]
await msg.edit(content=chunks[0])
for chunk in chunks[1:]: await ctx.send(chunk)
except Exception as e:
await msg.edit(content=“Error: “+str(e))

@bot.command(name=“scan”)
async def scan(ctx):
await ctx.send(“Scanning “+str(len(WATCHLIST))+” tickers…”)
snipes,waiting,forming=[],[],[]
for t in WATCHLIST:
try:
a=wizard(t); v=””; score=0
for line in a.split(”\n”):
if “VERDICT:” in line: v=line.split(“VERDICT:”)[-1].strip()
if “CONFLUENCE:” in line:
try: score=int(line.split(“CONFLUENCE:”)[-1].strip().split(”/”)[0].strip())
except: pass
if “SNIPE IT” in v: snipes.append(t+”[”+str(score)+”]”); await ctx.send(“SNIPE “+t+”\n”+a[:1800])
elif “WAIT” in v: waiting.append(t+”[”+str(score)+”]”)
elif “FORMING” in v: forming.append(t)
except: pass
s=“SCAN “+datetime.now().strftime(”%H:%M ET”)+”\n”
if snipes: s+=“SNIPE IT: “+” | “.join(snipes)+”\n”
if waiting: s+=“WAIT: “+” | “.join(waiting)+”\n”
if forming: s+=“FORMING: “+” | “.join(forming)+”\n”
if not snipes and not waiting: s+=“No setups. Patience is the strategy.”
await ctx.send(s)

@bot.command(name=“energy”)
async def energy(ctx):
await ctx.send(“Scanning energy sector…”)
for t in [“XLE”,“XOM”,“EOG”,“SLB”,“WTI”]:
try:
result=wizard(t)
await ctx.send(result[:1900])
except Exception as e:
await ctx.send(“Error on “+t+”: “+str(e))

@bot.command(name=“help”)
async def help_cmd(ctx):
await ctx.send(“MARKET WIZARD\n!analyze [TICKER] - full doctrine\n!scan - scan all “+str(len(WATCHLIST))+” tickers\n!energy - energy sector deep scan\n!help - this menu\nWatchlist: “+”, “.join(WATCHLIST)+”\nMin 3:1 RR. SNIPE IT = all 6 L7 confirmed.”)

bot.run(DISCORD_TOKEN)