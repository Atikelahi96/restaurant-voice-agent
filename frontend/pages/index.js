import React, { useEffect, useRef, useState, useCallback } from "react";
import { Mic2, CheckCircle2, ShoppingCart, Send } from "lucide-react";

const WS_AUDIO = "ws://localhost:8000/ws/audio";
const WS_TEXT  = "ws://localhost:8000/ws/text";
const OUTPUT_SAMPLE_RATE = 24_000;     // backend streams 24-kHz PCM

export default function Home() {
  //  ──────────── STATE ────────────────────────────────────────────────
  const [status, setStatus]     = useState("Disconnected");
  const [isRec, setIsRec]       = useState(false);
  const [menu, setMenu]         = useState([]);
  const [cart, setCart]         = useState([]);
  const [total, setTotal]       = useState(null);
  const [submitted, setSubmitted]= useState(false);
  const [thankYou, setThankYou] = useState(null);
  const [msg, setMsg]           = useState("");     // chat input

  //  ─────────── WS & AUDIO REFS ───────────────────────────────────────
  const wsAudioRef = useRef(null);
  const wsTextRef  = useRef(null);
  const audioCtxRef= useRef(null);
  const hpRef      = useRef(null);
  const nextPlay   = useRef(0);
  const micCtxRef  = useRef(null);
  const micStreamRef=useRef(null);

  //  ─────────── AUDIO HELPERS ─────────────────────────────────────────
  const getAudioCtx = () => {
    if (!audioCtxRef.current) {
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC({ sampleRate: OUTPUT_SAMPLE_RATE });
      ctx.resume();
      const hp = ctx.createBiquadFilter();
      hp.type = "highpass"; hp.frequency.value = 20; hp.Q.value = 0.7;
      hp.connect(ctx.destination);
      audioCtxRef.current = ctx;
      hpRef.current = hp;
      nextPlay.current = ctx.currentTime;
    }
    return audioCtxRef.current;
  };

  const playPCM = (arrBuf) => {
    // Guard: only accept even-length buffers
    if (!(arrBuf instanceof ArrayBuffer) || arrBuf.byteLength < 2) return;
    
    // If byte length is odd, trim the last byte
    if (arrBuf.byteLength % 2 !== 0) {
      console.warn("Odd-length PCM packet detected. Trimming last byte.");
      arrBuf = arrBuf.slice(0, arrBuf.byteLength - 1);
    }

    const int16 = new Int16Array(arrBuf);
    const floats = Float32Array.from(int16, (i) => i / 32768);
    const ctx = getAudioCtx();
    if (nextPlay.current < ctx.currentTime) nextPlay.current = ctx.currentTime;
    const buf = ctx.createBuffer(1, floats.length, OUTPUT_SAMPLE_RATE);
    buf.getChannelData(0).set(floats);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const gain = ctx.createGain();
    gain.connect(hpRef.current);
    src.connect(gain);

    const t = nextPlay.current,
        fade = 0.005;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(1, t + fade);
    gain.gain.setValueAtTime(1, t + buf.duration - fade);
    gain.gain.linearRampToValueAtTime(0, t + buf.duration);
    src.start(t);
    nextPlay.current += buf.duration;
  };

  //  ─────────── MESSAGE HANDLER (shared) ───────────────────────────────
  const handleMsg = useCallback((raw) => {
    if (typeof raw !== "string") { playPCM(raw); return; }
    let m; try { m = JSON.parse(raw); } catch { return; }

    if (m.menu) {
      setMenu(m.menu);
    } else if (m.status === "added") {
      setCart(prev => {
        const same = prev.find(l => l.item === m.item);
        if (same) same.qty += m.qty;
        else prev.push({ item: m.item, qty: m.qty });
        return [...prev];
      });
      setSubmitted(false);
    } else if (m.status === "submitted") {
      setTotal(m.total);
      setSubmitted(true);
      setThankYou({ id: m.order_id, total: m.total });
      // keep cart so user sees what they ordered
    }
  }, []);

  //  ─────────── OPEN BOTH WEBSOCKETS ───────────────────────────────────
  useEffect(() => {
    const open = (url, ref) => {
      const ws = new WebSocket(url); ws.binaryType = "arraybuffer";
      ws.onopen  = () => setStatus(s => `${url.includes("audio")?"🎙":"💬"} connected`);
      ws.onclose = () => { setStatus("Disconnected"); setTimeout(() => open(url, ref), 2500); };
      ws.onerror = e => { console.error("WS error", e); ws.close(); };
      ws.onmessage = e => handleMsg(e.data);
      ref.current = ws;
    };
    open(WS_AUDIO, wsAudioRef);
    open(WS_TEXT , wsTextRef );
    return () => { wsAudioRef.current?.close(); wsTextRef.current?.close(); };
  }, [handleMsg]);

  //  ─────────── RECORDING TOGGLE ───────────────────────────────────────
  const toggleRec = async () => {
    if (isRec) {
      micCtxRef.current?.close();
      micStreamRef.current?.getTracks().forEach(t => t.stop());
      setIsRec(false); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
      micStreamRef.current = stream;
      const AC = window.AudioContext || window.webkitAudioContext;
      const mic = new AC({ sampleRate: 16_000 });
      await mic.audioWorklet.addModule("/worklet-processor.js");
      const node = new AudioWorkletNode(mic, "mic-processor");
      node.port.onmessage = e => {
        if (wsAudioRef.current?.readyState === WebSocket.OPEN) wsAudioRef.current.send(e.data);
      };
      const src = mic.createMediaStreamSource(stream);
      const zero = mic.createGain(); zero.gain.value = 0;
      src.connect(node); node.connect(zero); zero.connect(mic.destination);
      micCtxRef.current = mic; setIsRec(true); getAudioCtx();
    } catch (err) { console.error(err); }
  };

  //  ─────────── SEND TEXT MESSAGE ───────────────────────────────────────
  const sendText = () => {
    if (!msg.trim()) return;
    wsTextRef.current?.readyState === WebSocket.OPEN &&
      wsTextRef.current.send(JSON.stringify({ text: msg }));   // Gemini will just read the raw string
    setMsg("");
  };

  //  ─────────── UI COMPONENTS ───────────────────────────────────────────
  const CartPanel = () => (
    <div className="fixed right-4 top-20 z-30 w-60 bg-blue-800/70 rounded-xl p-4 text-blue-50">
      <h3 className="font-semibold mb-2 flex items-center"><ShoppingCart size={18} className="mr-2"/>Cart</h3>
      {cart.length===0 ? <p className="text-sm opacity-80">No items yet…</p> :
        cart.map(l=>(<div key={l.item} className="flex justify-between text-sm"><span>{l.qty}× {l.item}</span></div>))}
      {total && <p className="mt-3 font-bold">Total ${total}</p>}
      {submitted && <p className="text-xs text-green-300 mt-1">Submitted ✓</p>}
    </div>
  );

  const MenuPanel = () => (
    <div className="fixed left-4 top-20 z-30 w-60 bg-blue-800/70 rounded-xl p-4 text-blue-50 max-h-[70vh] overflow-y-auto">
      <h3 className="font-semibold mb-2">Menu</h3>
      {menu.map(m=>(<div key={m.id} className="flex justify-between text-sm border-b border-blue-600/40 py-1"><span>{m.name}</span><span>${m.price}</span></div>))}
    </div>
  );

  const ThankYouCard = () => (
    <div className="fixed inset-0 flex items-center justify-center z-40">
      <div className="bg-blue-800/90 p-10 rounded-2xl shadow-xl text-center">
        <CheckCircle2 size={48} className="text-green-300 mx-auto mb-4"/>
        <h2 className="text-2xl text-blue-50 font-semibold mb-2">Order #{thankYou.id}</h2>
        <p className="text-blue-100 mb-4">Thank you! Your total is <span className="font-bold">${thankYou.total}</span>.</p>
        <button onClick={()=>setThankYou(null)} className="mt-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white">Close</button>
      </div>
    </div>
  );

  //  ─────────── RENDER ──────────────────────────────────────────────────
  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* BG */}
      <div className="absolute inset-0 bg-[url('/images/bg.jpg')] bg-cover bg-center filter blur-sm
                      before:content-[''] before:absolute before:inset-0 before:bg-blue-950/60" />

      {/* NAVBAR */}
      <nav className="relative z-20 flex items-center justify-between bg-blue-800/90 p-4">
        <h1 className="text-3xl font-bold text-blue-50">🎙 Café Assistant</h1>
        <button onClick={toggleRec}
                className="flex items-center space-x-2 rounded-full bg-blue-600 hover:bg-blue-500 px-4 py-2 text-white">
          <Mic2 size={20}/><span>{isRec?"Stop":"Talk"}</span>
        </button>
      </nav>

      {/* PANELS */}
      {menu.length>0 && <MenuPanel/>}
      <CartPanel/>

      {/* TEXT CHAT INPUT */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 flex w-[90%] max-w-lg z-30">
        <input value={msg} onChange={e=>setMsg(e.target.value)}
               onKeyDown={e=>e.key==="Enter"&&sendText()}
               placeholder="Type an order or question…"
               className="flex-1 rounded-l-lg px-3 py-2 bg-blue-100 border border-blue-300 focus:outline-none"/>
        <button onClick={sendText}
                className="rounded-r-lg bg-blue-600 hover:bg-blue-500 px-4 flex items-center justify-center text-white">
          <Send size={18}/>
        </button>
      </div>

      {/* THANK YOU */}
      {thankYou && <ThankYouCard/>}

      {/* STATUS */}
      <div className="fixed bottom-2 right-3 text-xs text-blue-100/80">{status}</div>
    </div>
  );
}
