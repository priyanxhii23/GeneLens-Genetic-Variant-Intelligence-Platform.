/**
 * Canvas DNA double helix with floating molecular particles.
 * - Depth-shaded strands (two sugar-phosphate backbones, phase-shifted by π)
 * - Base-pair rungs coloured by nucleotide pairing (A–T, G–C)
 * - Pointer parallax; pauses when off-screen; static frame for reduced motion
 */
import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import { useTheme } from "../lib/theme";

interface Props { className?: string; orientation?: "horizontal" | "vertical"; density?: number; particles?: number }

export default function DnaHelix({ className = "", orientation = "horizontal", density = 1, particles = 70 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();
  const { theme } = useTheme();

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(`--${n}`).trim().split(/\s+/).join(",");
    const C = { a: css("accent"), b: css("violet"), c: css("accent2"), d: css("plp"), ink: css("muted") };
    const pairColors = [[C.a, C.b], [C.c, C.d]];
    let w = 0, h = 0, dpr = 1, raf = 0, visible = true;
    const pointer = { x: 0, y: 0 };
    const seq = Array.from({ length: 400 }, (_, i) => (Math.sin(i * 12.9898) * 43758.5453) % 1 > 0 ? 0 : 1);
    const parts = Array.from({ length: particles }, () => ({
      x: Math.random(), y: Math.random(), z: Math.random(), vx: (Math.random() - 0.5) * 0.00025,
      vy: (Math.random() - 0.5) * 0.00025, r: 0.6 + Math.random() * 2.2, hue: Math.random() < 0.7 ? C.a : C.b,
    }));

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);
      // particles
      for (const p of parts) {
        if (!reduce) { p.x = (p.x + p.vx + 1) % 1; p.y = (p.y + p.vy + 1) % 1; }
        const px = p.x * w + pointer.x * 18 * p.z, py = p.y * h + pointer.y * 18 * p.z;
        ctx.beginPath();
        ctx.fillStyle = `rgba(${p.hue},${0.12 + p.z * 0.35})`;
        ctx.arc(px, py, p.r * (0.5 + p.z), 0, Math.PI * 2);
        ctx.fill();
      }
      const horizontal = orientation === "horizontal";
      const length = horizontal ? w : h;
      const across = horizontal ? h : w;
      const amp = Math.min(across * 0.22, 120);
      const centre = across / 2 + (horizontal ? pointer.y : pointer.x) * 10;
      const step = 14 / density;
      const phase = t * 0.00055;
      const pts: { s: number; a: number; z: number; i: number }[][] = [[], []];
      for (let s = -20, i = 0; s < length + 20; s += step, i++) {
        const th = s * 0.018 + phase;
        for (let k = 0; k < 2; k++) {
          const ang = th + k * Math.PI;
          pts[k].push({ s, a: centre + Math.sin(ang) * amp, z: (Math.cos(ang) + 1) / 2, i });
        }
      }
      const P = (s: number, a: number): [number, number] => (horizontal ? [s, a] : [a, s]);
      // rungs (behind strands where depth is low)
      for (let j = 0; j < pts[0].length; j += 2) {
        const p0 = pts[0][j], p1 = pts[1][j];
        const depth = (p0.z + p1.z) / 2;
        const [c0, c1] = pairColors[seq[(p0.i + 400) % 400]];
        const [x0, y0] = P(p0.s, p0.a); const [x1, y1] = P(p1.s, p1.a);
        const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
        ctx.lineWidth = 1.6;
        ctx.strokeStyle = `rgba(${c0},${0.15 + depth * 0.35})`;
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(mx, my); ctx.stroke();
        ctx.strokeStyle = `rgba(${c1},${0.15 + depth * 0.35})`;
        ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(x1, y1); ctx.stroke();
      }
      // backbones as depth-shaded beads
      for (let k = 0; k < 2; k++) {
        for (const p of pts[k]) {
          const [x, y] = P(p.s, p.a);
          const r = 1.4 + p.z * 3.2;
          ctx.beginPath();
          ctx.fillStyle = `rgba(${k ? C.b : C.a},${0.25 + p.z * 0.7})`;
          if (p.z > 0.75) { ctx.shadowColor = `rgba(${k ? C.b : C.a},0.8)`; ctx.shadowBlur = 12; } else ctx.shadowBlur = 0;
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.shadowBlur = 0;
    };

    const loop = (t: number) => { if (visible) draw(t); raf = requestAnimationFrame(loop); };
    const onMove = (e: PointerEvent) => { pointer.x = e.clientX / window.innerWidth - 0.5; pointer.y = e.clientY / window.innerHeight - 0.5; };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(canvas);
    resize();
    window.addEventListener("resize", resize);
    if (reduce) draw(0); else { window.addEventListener("pointermove", onMove); raf = requestAnimationFrame(loop); }
    return () => { cancelAnimationFrame(raf); io.disconnect(); window.removeEventListener("resize", resize); window.removeEventListener("pointermove", onMove); };
  }, [reduce, theme, orientation, density, particles]);

  return <canvas ref={ref} className={`pointer-events-none block h-full w-full ${className}`} aria-hidden />;
}
