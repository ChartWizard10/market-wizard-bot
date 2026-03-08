import os,base64,discord,anthropic,yfinance as yf,pandas as pd,numpy as np
from discord.ext import commands
from datetime import datetime

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
WATCHLIST = ["SPY","QQQ","NVDA","AAPL","MSFT","TSLA","AMZN","META","GOOGL","AMD","XLE","GLD","WTI","SLB","EOG","XOM"]
WIZARD = base64.b64decode(“WW91IGFyZSB0aGUgTWFya2V0IFdpemFyZC4gRWxpdGUgaW5zdGl0dXRpb25h”+“bCBhbmFseXN0LiBTbWFydCBtb25leSBkb2N0cmluZSBvbmx5LiBFdmVyeSBv”+“dXRwdXQgaXMgcHJlY2lzZSBhbmQgZGVwbG95LXJlYWR5LgoKRE9DVFJJTkUg”+“djQuMCAtIGV4ZWN1dGUgZXZlcnkgbGF5ZXIgaW4gZXhhY3Qgb3JkZXI6CgpM”+“MCBFTlZJUk9OTUVOVDogVklYPDE1PWZ1bGwgc2l6ZS4gVklYIDE1LTI1PXJl”+“ZHVjZWQuIFZJWD4yNT1taW5pbWFsL2Nhc2guIERYWSB1cD1yaXNrIG9mZi4g”+“WWllbGRzIHJpc2luZyBmYXN0PWVxdWl0eSBoZWFkd2luZC4gTWFqb3IgY2Fs”+“ZW5kYXIgZXZlbnQgaW4gMjRIPXJlZHVjZSBzaXplLiBTZXQgbWFjcm8gYmlh”+“czogYnVsbGlzaC9uZXV0cmFsL2JlYXJpc2guCgpMMSBJTlNUSVRVVElPTkFM”+“IENZQ0xFOiBBY2N1bXVsYXRpb249cXVpZXQgbG93IHZvbHVtZSB0aWdodCBy”+“YW5nZSBzbWFydCBtb25leSBsb2FkaW5nLiBTd2VlcD1lbmdpbmVlcmVkIHN0”+“b3AgaHVudCBsaXF1aWRpdHkgZ3JhYi4gRXhwYW5zaW9uPXJlYWwgbW92ZSBo”+“aWdoIHZvbHVtZSBkaXJlY3Rpb25hbC4gRGlzdHJpYnV0aW9uPXRvcHBpbmcg”+“YWN0aW9uIHZvbHVtZSBkcnlpbmcuIEhhcyBzd2VlcCBoYXBwZW5lZD8gSGFz”+“IE1TUyBjb25maXJtZWQ/IE5vIHN3ZWVwICsgbm8gTVNTID0gd2FpdC4KCkwy”+“IExJUVVJRElUWSBNQVBQSU5HOiBNYXJrIGV2ZXJ5IHBvb2wuIEVxdWFsIGhp”+“Z2hzPWJ1eSBzdG9wcyBhYm92ZS4gRXF1YWwgbG93cz1zZWxsIHN0b3BzIGJl”+“bG93LiBQcmV2IGRheSBIL0w9bW9zdCB3YXRjaGVkLiBSYW5nZSBIL0w9Y29t”+“cHJlc3Npb24gdGFyZ2V0cy4gUHJpb3Igc3dpbmcgSC9MPW1ham9yIHBvb2xz”+“LiBSb3VuZCBudW1iZXJzPXBzeWNob2xvZ2ljYWwgbWFnbmV0cy4gS2V5IHF1”+“ZXN0aW9uOiB3aGljaCBwb29sIGlzIHByaWNlIGRyYXduIHRvIG5leHQ/CgpM”+“MyBPUkRFUiBCTE9DSzogTGFzdCBiZWFyaXNoIGNhbmRsZSBiZWZvcmUgZGlz”+“cGxhY2VtZW50IG1vdmUgdXAuIERpZCBkaXNwbGFjZW1lbnQgYnJlYWsgc3Ry”+“dWN0dXJlPyBZZXM9dmFsaWQuIERpZCBpdCBsZWF2ZSBGVkc/IFllcz1UaWVy”+“MSBPQi4gTWFyayB6b25lIHRvcCB0byBib3R0b20uIFRoaXMgaXMgc3RvcCBh”+“bmNob3IuIFByaWNlIG11c3QgaG9sZCBhYm92ZSBpdC4KCkw0IEZWRzogQ2Fu”+“ZGxlMSBISUdIIHRvIENhbmRsZTMgTE9XID0gYnVsbGlzaCBGVkcgem9uZS4g”+“TWFyayBUb3AvNTBwY3QgRVEvQm90dG9tLiBEZWZhdWx0IGVudHJ5PTUwcGN0”+“IEVRLiBTdG9wPWJlbG93IE9CLiBOZXZlciBlbnRlciBGVkcgd2l0aG91dCBj”+“b25maXJtZWQgTVNTIGFib3ZlIGl0LgoKTDUgUEFUVEVSTlM6IFRpZXIxKCsy”+“cHRzKTogQnVsbCBGbGFnLCBDdXAgYW5kIEhhbmRsZSwgQXNjZW5kaW5nIFRy”+“aWFuZ2xlLCBEb3VibGUgQm90dG9tLCBCdWxsIFBlbm5hbnQuIFRpZXIyKCsx”+“cHQpOiBGYWxsaW5nIFdlZGdlLCBJbnZlcnNlIEgmUywgQnVsbGlzaCBFbmd1”+“bGZpbmcsIE1vcm5pbmcgU3RhciwgUm91bmRpbmcgQm90dG9tLiBUaWVyMzog”+“VGhyZWUgV2hpdGUgU29sZGllcnMsIEhhbW1lciwgUmlzaW5nIENoYW5uZWws”+“IEdvbGRlbiBDcm9zcy4gU3RydWN0dXJlK1BhdHRlcm49bWF4aW11bSBjb252”+“aWN0aW9uLiBQYXR0ZXJuIGFsb25lPXdlYWsuCgpMNiBNVEYgU0NPUkU6IE1v”+“bnRobHkvV2Vla2x5L0RhaWx5LzRILzFILiA1LzU9ZnVsbCBzaXplLiA0LzU9”+“c3RhbmRhcmQuIDMvNT1yZWR1Y2VkLiBMZXNzIHRoYW4gMz1ubyB0cmFkZS4K”+“Ckw3IEVOVFJZIENIRUNLTElTVCBhbGwgNiByZXF1aXJlZCBmb3IgU05JUEUg”+“SVQ6IDEtTGlxdWlkaXR5IHN3ZWVwIGNvbmZpcm1lZC4gMi1NU1MgY29uZmly”+“bWVkIGhpZ2hlciBoaWdoIG1hZGUuIDMtUHJpY2UgcmV0cmFjaW5nIGludG8g”+“RlZHLiA0LVByaWNlIGF0IDUwcGN0IEVRLiA1LVZvbHVtZSBjb250cmFjdGlu”+“ZyBvbiByZXRyYWNlbWVudC4gNi1Db25maXJtYXRpb24gY2FuZGxlIGZvcm1p”+“bmcuIEFsbCA2PVNOSVBFIElULiBNaXNzaW5nIGFueT1XQUlULgoKTDggVEFS”+“R0VUUzogVDE9bmVhcmVzdCBsaXF1aWRpdHkgcG9vbC4gVDI9bmV4dCBtYWpv”+“ciBwb29sLiBSdW5uZXI9ZGlzdGFudCBwb29sLiBNaW5pbXVtIFJSPTM6MS4g”+“QmVsb3cgMzoxPWRlY2xpbmUgYWx3YXlzLgoKTDkgUklTSzogU2l6ZT0oQWNj”+“b3VudCB4IDEtMiUpIGRpdmlkZWQgYnkgKEVudHJ5IG1pbnVzIE9CIHN0b3Ap”+“LiBWSVg+MjA9Y3V0IDUwcGN0LiBOZXZlciBhdmVyYWdlIGRvd24uIE5ldmVy”+“IHJlbW92ZSBzdG9wLgoKNCBERU1BTkQgRUxFTUVOVFMgYWxsND1lbnRlciwg”+“Mz1yZWR1Y2VkLCBsZXNzIHRoYW4gMz1ub2lzZTogRGlzcGxhY2VtZW50ICsg”+“TGlxdWlkaXR5IFN3ZWVwICsgRlZHIEltYmFsYW5jZSArIE1TUyBDb25maXJt”+“ZWQuCgpCUkVBS0VSIEJMT0NLOiBQcmlvciBiZWFyaXNoIE9CIHZpb2xhdGVk”+“IGJ5IGJ1bGxpc2ggbW92ZS4gT2xkIHJlc2lzdGFuY2U9bmV3IHN1cHBvcnQu”+“IERvdWJsZSBkZW1hbmQgem9uZS4gVGllciBBIGVudHJ5IG9uIHJldGVzdC4K”+“CkNPTkZMVUVOQ0UgbWF4IDEwOiArMiBUaWVyMSBwYXR0ZXJuLiArMSBlYWNo”+“OiBzd2VlcCwgTVNTLCBGVkcgaG9sZGluZywgT0IgdmFsaWQsIE1URiAzLzUr”+“LCB2b2wgZXhwYW5zaW9uLCB2b2wgY29udHJhY3Rpb24sIEVNQSBzdGFjayAy”+“MD41MD4yMDAuCgpPUFRJT05TOiBFYXJseSBleHBhbnNpb249aGlnaCBkZWx0”+“YSBjYWxscyAwLjcwLTAuODVEIDMwLTQ1RFRFLiBDb25maXJtZWQgYnJlYWtv”+“dXQ9SVRNIGNhbGwgb3IgOTBEVEUgc3ByZWFkLiBCcmVha2VyIHJldGVzdD1B”+“VE0gNDVEVEUuIExhdGUgc3RhZ2U9U1RBTkQgRE9XTi4KCkVORVJHWSBmb3Ig”+“WExFLFhPTSxFT0csU0xCLFdUSTogQ3J1ZGUgZGlyZWN0aW9uLCBPUEVDLCBE”+“WFkgaW1wYWN0LCBzZWFzb25hbCBkZW1hbmQsIHJpZyBjb3VudC4gV1RJIGFi”+“b3ZlIDgwPWJ1bGxpc2guIEJlbG93IDcwPWJlYXJpc2guCgpHT0xEIGZvciBH”+“TEQ6IERYWSBpbnZlcnNlLCByZWFsIHlpZWxkcyBkaXJlY3Rpb24sIEZlZCBi”+“aWFzLCBzYWZlIGhhdmVuIGZsb3dzLCBjZW50cmFsIGJhbmsgYnV5aW5nLiBB”+“Ym92ZSAyMDBFTUEgd2l0aCBmYWxsaW5nIHJlYWwgeWllbGRzPW1heGltdW0g”+“YnVsbGlzaC4KCk9VVFBVVCBGT1JNQVQ6CldJWkFSRCBbVElDS0VSXSBbREFU”+“RSBUSU1FXQpMMDogVklYW3hdIFNpemU6W2Z1bGwvcmVkdWNlZC9taW5pbWFs”+“XSBCaWFzOltidWxsL25ldXRyYWwvYmVhcl0gRXZlbnRSaXNrOlt5L25dCkwx”+“OiBQaGFzZTpbeF0gU3dlZXA6W3kvbl0gTVNTOlt5L25dCkwyOiBEcmF3blRv”+“OiRbeF0gcmVhc29uOlt4XSBQb29sQWJvdmU6JFt4XSBQb29sQmVsb3c6JFt4”+“XQpMMzogT0IgJFtsb10tJFtoaV0gVmFsaWQ6W3kvbl0KTDQ6IEZWRyAkW2Jv”+“dF0tJFtlcV0tJFt0b3BdIEVudHJ5OiRbeF0gU3RvcDokW3hdCkw1OiBbUGF0”+“dGVybl0gVFsxLzIvM10gW0NvbmZpcm1lZC9Gb3JtaW5nL0Fic2VudF0gQnJl”+“YWtlcjpbeS9uXQpMNjogTVt5L25dV1t5L25dRFt5L25dNEhbeS9uXTFIW3kv”+“bl0gU2NvcmU6W3hdLzUKTDc6IENvbmZpcm1lZDpbbGlzdF0gTWlzc2luZzpb”+“bGlzdF0gVGllcjpbQS9CL0NdIEVudHJ5OiRbeF0gSW52YWxpZDokW3hdCkw4”+“OiBUMTokW3hdIFQyOiRbeF0gUnVubmVyOiRbeF0gUlI6W3hdOjEKTDk6IFNp”+“emU9KEFjY3QgeCAxcGN0KS9beF0gVklYYWRqOlt5L25dCk9QVElPTlM6ICRb”+“c3RyaWtlXSBbZXhwaXJ5XSBbdHlwZV0gW3JhdGlvbmFsZV0KQ09ORkxVRU5D”+“RTogW1gvMTBdClZFUkRJQ1Q6IFtTTklQRSBJVCAvIFdBSVQgRk9SIEVOVFJZ”+“IC8gUEFUVEVSTiBGT1JNSU5HIC8gU1RBTkQgRE9XTl0KRURHRTogW29uZSBz”+“ZW50ZW5jZSBoaWdoZXN0IGNvbnZpY3Rpb24gcmVhc29uXQoKU2NvcmUgYmVs”+“b3cgNzogTU9OSVRPUklORyBbVElDS0VSXSAtIFtyZWFzb25dIC0gcmV2aXNp”+“dCBhdCAkW2xldmVsXQoKTEFXUzogU05JUEUgSVQgb25seSBhbGwgNiBMNyBj”+“b25maXJtZWQuIFJSIGJlbG93IDM6MT1kZWNsaW5lIGFsd2F5cy4gVklYIGFi”+“b3ZlIDI1PW5vIGZ1bGwgc2l6ZS4gTGVzcyB0aGFuIDMgZGVtYW5kIGVsZW1l”+“bnRzPWlnbm9yZS4gTVRGIGJlbG93IDMvNT1tYXggV0FJVC4gRGlzdHJpYnV0”+“aW9uPW5vIGVudHJpZXMuCgpUSEUgTEFXOiBNYXJrIHRoZSBwb29scy4gV2Fp”+“dCBmb3IgdGhlIHN3ZWVwLiBDb25maXJtIHRoZSBNU1MuIEVudGVyIHRoZSBG”+“VkcuIFRhcmdldCB0aGUgb3Bwb3NpbmcgcG9vbC4gRW52aXJvbm1lbnQuQ3lj”+“bGUuTGlxdWlkaXR5LlN0cnVjdHVyZS5PQi5GVkcuTVNTLkVudHJ5LlRhcmdl”+“dC4gVGhhdCBvcmRlci4gRXZlcnkgdGltZS4gTm8gZXhjZXB0aW9ucy4=”).decode()

def fetch(ticker):
try:
df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
if df.empty:
return {}
c = df["Close"].squeeze()
h = df["High"].squeeze()
l = df["Low"].squeeze()
v = df["Volume"].squeeze()
o = df["Open"].squeeze()
e20 = c.ewm(span=20, adjust=False).mean()
e50 = c.ewm(span=50, adjust=False).mean()
e200 = c.ewm(span=200, adjust=False).mean()
d = c.diff()
rsi = 100 - (100 / (1 + d.clip(lower=0).rolling(14).mean() / (-d.clip(upper=0)).rolling(14).mean().replace(0, np.nan)))
tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
atr = tr.rolling(14).mean().iloc[-1]
vol_r = float(v.iloc[-1] / v.rolling(20).mean().iloc[-1])
cur = float(c.iloc[-1])
sh = float(h.tail(60).max())
sl = float(l.tail(60).min())
fr = sh - sl
h52 = float(h.tail(252).max())
l52 = float(l.tail(252).min())
fvg = next(({"top": round(float(l.values[i+2]), 2), "eq": round((float(l.values[i+2]) + float(h.values[i])) / 2, 2), "bot": round(float(h.values[i]), 2)} for i in range(len(df)-20, len(df)-2) if l.values[i+2] > h.values[i]), None)
ob = next(({"hi": round(float(o.values[i]), 2), “lo”: round(float(c.values[i]), 2)} for i in range(len(df)-20, len(df)-3) if c.values[i] < o.values[i] and c.values[i+1] > o.values[i+1] * 1.005), None)
rl = float(l.tail(10).min())
pl = float(l.tail(20).min())
sweep = rl < pl * 0.998
rh = float(h.tail(5).max())
ph = float(h.tail(20).iloc[:-5].max())
mss = sweep and rh > ph
return dict(
ticker=ticker, cur=round(cur, 2), h52=round(h52, 2), l52=round(l52, 2),
h20=round(float(h.tail(20).max()), 2), l20=round(float(l.tail(20).min()), 2),
e20=round(float(e20.iloc[-1]), 2), e50=round(float(e50.iloc[-1]), 2),
e200=round(float(e200.iloc[-1]), 2), rsi=round(float(rsi.iloc[-1]), 1),
vol_r=round(vol_r, 2), atr=round(float(atr), 2),
bull=float(e20.iloc[-1]) > float(e50.iloc[-1]) > float(e200.iloc[-1]),
cons=bool(tr.rolling(5).mean().iloc[-1] < tr.rolling(20).mean().iloc[-1] * 0.75),
f382=round(sh - fr * 0.382, 2), f618=round(sh - fr * 0.618, 2),
e1618=round(sh + fr * 0.618, 2), sh=round(sh, 2), sl=round(sl, 2),
fvg=fvg, ob=ob, sweep=sweep, mss=mss,
eqhi=round(float(h.tail(10).max()), 2), eqlo=round(float(l.tail(10).min()), 2),
pct=round((cur - h52) / h52 * 100, 1),
ohlcv=df.tail(10)[["Open", "High", "Low", "Close", "Volume"]].round(2).to_string()
)
except Exception as e:
return {"error": str(e)}

def build_prompt(d):
fvg = “FVG Top $” + str(d["fvg"]["top"]) + " EQ $" + str(d["fvg"]["eq"]) + " Bot $" + str(d["fvg"]["bot"]) if d.get("fvg") else "No FVG"
ob = "OB $" + str(d["ob"]["lo"]) + "-$" + str(d["ob"][“hi”]) if d.get(“ob”) else “No OB”
return (
"LIVE DATA " + d["ticker"] + " " + datetime.now().strftime("%Y-%m-%d %H:%M ET") +
"\nPrice $" + str(d["cur"]) + " 52W $" + str(d["h52"]) + "/$" + str(d["l52"]) + " (" + str(d["pct"]) + "%)" +
"\nEMA 20=$" + str(d["e20"]) + " 50=$" + str(d["e50"]) + " 200=$" + str(d["e200"]) + " Stack " + ("BULL" if d["bull"] else "BEAR") +
"\nRSI " + str(d["rsi"]) + " Vol " + str(d["vol_r"]) + "x ATR $" + str(d["atr"]) +
"\nSweep " + ("YES" if d["sweep"] else "NO") + " MSS " + ("YES" if d["mss"] else "NO") +
"\n" + fvg + "\n" + ob +
"\nEqHi $" + str(d["eqhi"]) + " EqLo $" + str(d["eqlo"]) +
"\nFib 0.382=$" + str(d["f382"]) + " 0.618=$" + str(d["f618"]) +
"\nOHLCV:\n" + d["ohlcv"] +
"\nRun full Doctrine v4.0. Score 1-10. 7+=full. Less than 7=MONITORING. Min 3:1 RR."
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def wizard(ticker):
d = fetch(ticker.upper())
if not d or "error" in d:
return "Cannot fetch " + ticker
r = ai.messages.create(model="claude-sonnet-4-6", max_tokens=1800, system=WIZARD, messages=[{"role": "user", “content”: build_prompt(d)}])
return r.content[0].text

@bot.event
async def on_ready():
print("Market Wizard LIVE " + str(bot.user))

@bot.command(name="analyze")
async def analyze(ctx, ticker: str = None):
if not ticker:
await ctx.send("Usage: !analyze NVDA")
return
msg = await ctx.send("Running doctrine on " + ticker.upper() + "…")
try:
result = wizard(ticker)
chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
await msg.edit(content=chunks[0])
for chunk in chunks[1:]:
await ctx.send(chunk)
except Exception as e:
await msg.edit(content="Error: " + str(e))

@bot.command(name="scan")
async def scan(ctx):
await ctx.send("Scanning" + str(len(WATCHLIST)) + "tickers…")
snipes, waiting, forming = [], [], []
for t in WATCHLIST:
try:
a = wizard(t)
v = ""
score = 0
for line in a.split("\n"):
if "VERDICT:" in line:
v = line.split("VERDICT:")[-1].strip()
if "CONFLUENCE:" in line:
try:
score = int(line.split("CONFLUENCE:")[-1].strip().split("/")[0].strip())
except:
pass
if "SNIPE IT" in v:
snipes.append(t + "[" + str(score) + "]")
await ctx.send("SNIPE" + t + "\n" + a[:1800])
elif "WAIT" in v:
waiting.append(t + "[" + str(score) + "]")
elif "FORMING" in v:
forming.append(t)
except:
pass
s = "SCAN " + datetime.now().strftime("%H:%M ET") + "\n"
if snipes:
s += "SNIPE IT: " + " | ".join(snipes) + "\n"
if waiting:
s += "WAIT: " + " | ".join(waiting) + "\n"
if forming:
s += "FORMING: " + " | ".join(forming) + "\n"
if not snipes and not waiting:
s += "No setups. Patience is the strategy."
await ctx.send(s)

@bot.command(name="energy")
async def energy(ctx):
await ctx.send("Scanning energy sector…")
for t in ["XLE", "XOM", "EOG", "SLB", "WTI"]:
try:
await ctx.send(wizard(t)[:1900])
except Exception as e:
await ctx.send("Error on " + t + ": " + str(e))

@bot.command(name="help")
async def help_cmd(ctx):
await ctx.send("MARKET WIZARD\n!analyze [TICKER]\n!scan\n!energy\n!help\nWatchlist: " + ", ".join(WATCHLIST) + "\nMin 3:1 RR. SNIPE IT=all 6 L7 confirmed.")

bot.run(DISCORD_TOKEN)