import React, { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ArrowDown, ArrowRight } from 'lucide-react';

// Park-Miller Seeded Generator for Hero Constellation (Seed 5)
class ParkMiller {
  private s: number;
  constructor(seed: number) { this.s = seed; }
  next(): number {
    this.s = (this.s * 16807) % 2147483647;
    return this.s / 2147483647;
  }
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  angle: number;
  vRot: number;
  color: string;
  isFeather: boolean;
  age: number;
  life: number;
}

interface HeroExperienceProps {
  onEnterDashboard: () => void;
  onExplorePerson: () => void;
  onExploreNetwork?: () => void;
}

export const HeroExperience: React.FC<HeroExperienceProps> = ({
  onEnterDashboard,
  onExplorePerson,
  onExploreNetwork
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const heroLayerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const behindPanelRef = useRef<HTMLDivElement>(null);
  const dialRef = useRef<SVGSVGElement>(null);
  const scrollCueRef = useRef<HTMLButtonElement>(null);

  // Parallax Layer Refs
  const officerRef = useRef<HTMLDivElement>(null);
  const robotRef = useRef<HTMLDivElement>(null);
  const hourglassRef = useRef<HTMLDivElement>(null);
  const skylineRef = useRef<HTMLDivElement>(null);
  const orbitRef = useRef<SVGSVGElement>(null);
  const wordmarkRef = useRef<HTMLHeadingElement>(null);
  const headlineRef = useRef<HTMLParagraphElement>(null);
  const supportRef = useRef<HTMLParagraphElement>(null);
  const ctaGroupRef = useRef<HTMLDivElement>(null);

  // Side label hover contrast state
  const [mouseSide, setMouseSide] = useState<'left' | 'right' | null>(null);

  // Travelling dots on Ellipse B
  const [travellingDots, setTravellingDots] = useState<Array<{ x: number; y: number }>>([]);
  const [fallingSand, setFallingSand] = useState<Array<{ y: number; opacity: number }>>([
    { y: 430, opacity: 0.9 },
    { y: 445, opacity: 0.7 },
    { y: 460, opacity: 0.5 },
    { y: 475, opacity: 0.3 },
    { y: 490, opacity: 0.1 }
  ]);

  // Seeded Hero Constellation dots (Seed 5, 26 dots)
  const heroConstellation = React.useMemo(() => {
    const rng = new ParkMiller(5);
    const pts: Array<{ x: number; y: number; r: number }> = [];
    for (let i = 0; i < 26; i++) {
      pts.push({
        x: 400 + rng.next() * 800,
        y: 150 + rng.next() * 600,
        r: 1.5 + rng.next() * 2.5
      });
    }
    return pts;
  }, []);

  // GSAP Entrance & Layer Animations
  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

      // 1. Officer slides in from -90px
      if (officerRef.current) {
        tl.fromTo(officerRef.current, { x: -90, opacity: 0 }, { x: 0, opacity: 1, duration: 1.5 }, 0);
      }

      // 2. Robot slides in from +90px
      if (robotRef.current) {
        tl.fromTo(robotRef.current, { x: 90, opacity: 0 }, { x: 0, opacity: 1, duration: 1.5 }, 0.2);
      }

      // 3. Hourglass grows from 82%
      if (hourglassRef.current) {
        tl.fromTo(hourglassRef.current, { scale: 0.82, opacity: 0 }, { scale: 1, opacity: 1, duration: 1.5 }, 0.5);
      }

      // 4. Orbit Ellipses draw themselves
      if (orbitRef.current) {
        const ellipses = orbitRef.current.querySelectorAll('.orbit-path');
        tl.fromTo(
          ellipses,
          { strokeDashoffset: 1 },
          { strokeDashoffset: 0, duration: 2.4, stagger: 0.3, ease: 'power2.inOut' },
          0.6
        );
      }

      // 6. KRONOS wordmark rises
      if (wordmarkRef.current) {
        tl.fromTo(wordmarkRef.current, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1.1 }, 0.8);
      }

      // 7. Headline rises
      if (headlineRef.current) {
        tl.fromTo(headlineRef.current, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.9 }, 0.95);
      }

      // 8. Supporting line rises
      if (supportRef.current) {
        tl.fromTo(supportRef.current, { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8 }, 1.1);
      }

      // 9. CTA Buttons rise
      if (ctaGroupRef.current) {
        tl.fromTo(ctaGroupRef.current.children, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, stagger: 0.12 }, 1.2);
      }

      // 10. Skyline fades up from 30px below
      if (skylineRef.current) {
        tl.fromTo(skylineRef.current, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1.2 }, 1.3);
      }
    });

    return () => ctx.revert();
  }, []);

  // Travelling dots on Ellipse B & Falling Sand loop
  useEffect(() => {
    let angle = 0;
    let animId: number;

    const loop = () => {
      angle += 0.0011;
      const dots: Array<{ x: number; y: number }> = [];
      const cx = 805;
      const cy = 452;
      const rx = 600;
      const ry = 190;
      const rot = 0.0698; // 4 degrees in rad

      for (let i = 0; i < 6; i++) {
        const theta = angle + i * 1.047; // 60 degrees apart
        // Parametric ellipse formula
        const ex = rx * Math.cos(theta);
        const ey = ry * Math.sin(theta);
        // Rotate by 4 deg
        const rxRot = ex * Math.cos(rot) - ey * Math.sin(rot);
        const ryRot = ex * Math.sin(rot) + ey * Math.cos(rot);
        dots.push({ x: cx + rxRot, y: cy + ryRot });
      }
      setTravellingDots(dots);

      // Sand simulation
      setFallingSand(prev =>
        prev.map(s => {
          let ny = s.y + 0.8;
          let no = s.opacity - 0.008;
          if (ny > 500 || no <= 0) {
            ny = 430;
            no = 0.9;
          }
          return { y: ny, opacity: no };
        })
      );

      animId = requestAnimationFrame(loop);
    };

    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, []);

  // Mouse Parallax & Side-Label Brightness
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const nx = e.clientX / w - 0.5;
      const ny = e.clientY / h - 0.5;

      setMouseSide(nx < 0 ? 'left' : 'right');

      // GSAP smooth layer parallax
      if (officerRef.current) gsap.to(officerRef.current, { x: nx * -14, y: ny * -8, duration: 1.3, ease: 'power2.out', overwrite: 'auto' });
      if (robotRef.current) gsap.to(robotRef.current, { x: nx * 14, y: ny * -8, duration: 1.3, ease: 'power2.out', overwrite: 'auto' });
      if (hourglassRef.current) gsap.to(hourglassRef.current, { x: nx * 26, y: ny * 16, duration: 1.3, ease: 'power2.out', overwrite: 'auto' });
      if (skylineRef.current) gsap.to(skylineRef.current, { x: nx * -8, y: ny * -4, duration: 1.3, ease: 'power2.out', overwrite: 'auto' });
      if (orbitRef.current) gsap.to(orbitRef.current, { x: nx * 34, y: ny * 20, duration: 1.3, ease: 'power2.out', overwrite: 'auto' });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // Scroll Dissolve & Feather Spawner (Section 7)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let particles: Particle[] = [];
    let lastP = 0;
    let animFrame: number;

    const colors = ['#C69A55', '#B96D50', '#F8F3E9', '#DCCAB0', '#A86F45', '#D79A4A'];

    const resizeCanvas = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.scale(dpr, dpr);
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const onScroll = () => {
      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const scrollTop = -rect.top;
      const hwrapHeight = container.clientHeight;
      const vh = window.innerHeight;
      const range = (hwrapHeight - vh) * 0.7;

      const p = Math.max(0, Math.min(1, scrollTop / range));
      const e = p * p * (3 - 2 * p); // smoothstep

      // Radius R for radial mask
      const W = window.innerWidth;
      const H = window.innerHeight;
      const diag = Math.hypot(W, H);
      const R = e * diag * 0.62;

      // Mask center at Dial position
      let cx = W / 2;
      let cy = H * 0.40;
      if (dialRef.current) {
        const dRect = dialRef.current.getBoundingClientRect();
        cx = dRect.left + dRect.width / 2;
        cy = dRect.top + dRect.height / 2;
      }

      // Apply CSS mask to hero
      if (heroLayerRef.current) {
        if (p < 0.005) {
          heroLayerRef.current.style.maskImage = 'none';
          (heroLayerRef.current.style as any).webkitMaskImage = 'none';
          heroLayerRef.current.style.visibility = 'visible';
          heroLayerRef.current.style.pointerEvents = 'auto';
        } else if (p >= 0.995) {
          heroLayerRef.current.style.visibility = 'hidden';
          heroLayerRef.current.style.pointerEvents = 'none';
        } else {
          heroLayerRef.current.style.visibility = 'visible';
          const maskVal = `radial-gradient(circle at ${cx}px ${cy}px, transparent ${R}px, #000 ${R + 110}px)`;
          heroLayerRef.current.style.maskImage = maskVal;
          (heroLayerRef.current.style as any).webkitMaskImage = maskVal;
          heroLayerRef.current.style.pointerEvents = p > 0.25 ? 'none' : 'auto';
        }
      }

      // Behind panel reveal
      if (behindPanelRef.current) {
        const bOpacity = Math.max(0, Math.min(1, (p - 0.08) / 0.35));
        const bScale = 0.94 + 0.06 * e;
        behindPanelRef.current.style.opacity = String(bOpacity);
        behindPanelRef.current.style.transform = `scale(${bScale})`;
      }

      // Scroll Cue fade out
      if (scrollCueRef.current) {
        const cueOpacity = Math.max(0, 1 - p / 0.12);
        scrollCueRef.current.style.opacity = String(cueOpacity);
        scrollCueRef.current.style.pointerEvents = cueOpacity <= 0.05 ? 'none' : 'auto';
      }

      // Spawn Feathers & Sprinkles on delta p
      const dp = Math.abs(p - lastP);
      if (dp > 0.001 && p < 0.98) {
        const spawnCount = Math.min(60, Math.ceil(dp * 1800));
        for (let i = 0; i < spawnCount && particles.length < 420; i++) {
          const angle = Math.random() * Math.PI * 2;
          const spawnR = R + 40 + (Math.random() - 0.5) * (R * 0.16);
          const px = cx + Math.cos(angle) * spawnR;
          const py = cy + Math.sin(angle) * spawnR;

          // Skip if offscreen
          if (px < -40 || px > W + 40 || py < -40 || py > H + 40) continue;

          const baseSpeed = 0.6 + Math.random() * 2.2;
          const isFeather = Math.random() > 0.35; // 65% feathers, 35% sprinkles

          particles.push({
            x: px,
            y: py,
            vx: Math.cos(angle) * baseSpeed + 0.9, // Wind to right (+0.9)
            vy: Math.sin(angle) * baseSpeed - (0.5 + Math.random() * 0.8), // Upward lift
            size: isFeather ? 6 + Math.random() * 16 : 1.2 + Math.random() * 1.6,
            angle: Math.random() * Math.PI * 2,
            vRot: (Math.random() - 0.5) * 0.12,
            color: colors[Math.floor(Math.random() * colors.length)],
            isFeather,
            age: 0,
            life: 80 + Math.floor(Math.random() * 90)
          });
        }
      }
      lastP = p;
    };

    window.addEventListener('scroll', onScroll, { passive: true });

    // Particle render loop
    const renderParticles = () => {
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      for (let i = particles.length - 1; i >= 0; i--) {
        const pt = particles[i];
        pt.age++;
        if (pt.age >= pt.life) {
          particles.splice(i, 1);
          continue;
        }

        // Dynamics: Air drag 0.988, vertical lift -0.004, rotation
        pt.vx *= 0.988;
        pt.vy = pt.vy * 0.988 - 0.004;
        pt.x += pt.vx;
        pt.y += pt.vy;
        pt.angle += pt.vRot;

        const opacity = (1 - pt.age / pt.life) * 0.95;

        ctx.save();
        ctx.translate(pt.x, pt.y);
        ctx.rotate(pt.angle);
        ctx.globalAlpha = opacity;

        if (pt.isFeather) {
          // Leaf shape with quill
          const s = pt.size;
          ctx.fillStyle = pt.color;
          ctx.beginPath();
          ctx.moveTo(0, -s);
          ctx.quadraticCurveTo(s * 0.34, -s * 0.2, 0, s);
          ctx.quadraticCurveTo(-s * 0.34, -s * 0.2, 0, -s);
          ctx.fill();

          // Central quill
          ctx.strokeStyle = '#30251F';
          ctx.lineWidth = 0.8;
          ctx.globalAlpha = opacity * 0.7;
          ctx.beginPath();
          ctx.moveTo(0, -s * 1.1);
          ctx.lineTo(0, s * 0.8);
          ctx.stroke();
        } else {
          // Sprinkle dot
          ctx.fillStyle = pt.color;
          ctx.beginPath();
          ctx.arc(0, 0, pt.size, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.restore();
      }

      animFrame = requestAnimationFrame(renderParticles);
    };

    animFrame = requestAnimationFrame(renderParticles);

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animFrame);
    };
  }, []);

  // IntersectionObserver for Section 8 Story Blocks
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            gsap.fromTo(
              entry.target.children,
              { y: 30, opacity: 0 },
              { y: 0, opacity: 1, duration: 0.8, stagger: 0.1, ease: 'power2.out' }
            );
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.2 }
    );

    const storyBlocks = document.querySelectorAll('.story-block');
    storyBlocks.forEach(el => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  const handleScrollCueClick = () => {
    if (!containerRef.current) return;
    const hwrapHeight = containerRef.current.clientHeight;
    const vh = window.innerHeight;
    const targetY = (hwrapHeight - vh) * 0.75;
    window.scrollTo({ top: targetY, behavior: 'smooth' });
  };

  return (
    <div className="w-full">
      {/* 7.1 Pinning Wrapper (230vh tall) */}
      <div ref={containerRef} className="relative w-full h-[230vh]">
        {/* Sticky 100vh Viewport */}
        <div ref={stickyRef} className="sticky top-0 w-full h-screen overflow-hidden bg-[#FCE7CC]">
          {/* 7.4 Behind Panel (Revealed as Hero feathers dissolve) */}
          <div
            ref={behindPanelRef}
            className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-1 text-center px-6"
            style={{
              opacity: 0,
              transform: 'scale(0.94)',
              background: 'radial-gradient(circle at 50% 50%, rgba(198,154,85,.28), transparent 55%)'
            }}
          >
            <span className="font-mono text-xs uppercase tracking-[0.3em] text-[#B96D50] font-semibold mb-3">
              K R O N O S
            </span>
            <h2 className="font-serif text-3xl md:text-5xl lg:text-6xl text-[#30251F] max-w-4xl font-normal leading-tight">
              Where <span className="italic font-serif text-[#B96D50]">human judgement</span> meets{' '}
              <span className="italic font-serif text-[#A86F45]">machine intelligence</span>.
            </h2>
            <p className="font-sans text-xs md:text-sm text-[#433A32]/80 mt-4 max-w-xl font-light">
              Reconstructing multi-jurisdictional evidence timelines with cryptographic integrity and contextual graph reasoning.
            </p>
          </div>

          {/* 7.5 Feather & Sprinkle Particle Canvas (z-index 7) */}
          <canvas
            ref={canvasRef}
            className="absolute inset-0 pointer-events-none z-[7] w-full h-full"
          />

          {/* 5.1 & 7.3 Main Hero Stage with Radial Mask (z-index 5) */}
          <div
            ref={heroLayerRef}
            className="absolute inset-0 z-[5] w-full h-full overflow-hidden"
          >
            {/* 16:9 Aspect Ratio Container ('Stage') */}
            <div
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
              style={{
                width: 'max(100vw, 177.78vh)',
                aspectRatio: '16/9',
                containerType: 'size'
              }}
            >
              {/* Base Composite Artwork Backdrop */}
              <div
                className="absolute inset-0 bg-cover bg-center pointer-events-none"
                style={{ backgroundImage: `url('/assets/kronos-hero-artwork.jpg')` }}
              />

              {/* 5.2 Layer 1: Officer Layer with Parallax */}
              <div
                ref={officerRef}
                className="absolute pointer-events-none"
                style={{
                  left: 0,
                  top: '16.67%',
                  width: '33.75%',
                  height: '83.33%',
                  maskImage: 'linear-gradient(to right, black 65%, transparent 100%), linear-gradient(to bottom, transparent 0%, black 15%)',
                  WebkitMaskImage: 'linear-gradient(to right, black 65%, transparent 100%), linear-gradient(to bottom, transparent 0%, black 15%)'
                }}
              />

              {/* 5.2 Layer 2: Robot Layer with Parallax */}
              <div
                ref={robotRef}
                className="absolute pointer-events-none"
                style={{
                  left: '67.5%',
                  top: '7.78%',
                  width: '32.5%',
                  height: '92.22%',
                  maskImage: 'linear-gradient(to left, black 65%, transparent 100%), linear-gradient(to bottom, transparent 0%, black 12%)',
                  WebkitMaskImage: 'linear-gradient(to left, black 65%, transparent 100%), linear-gradient(to bottom, transparent 0%, black 12%)'
                }}
              />

              {/* 5.2 Layer 3: Hourglass Layer with Parallax */}
              <div
                ref={hourglassRef}
                className="absolute pointer-events-none"
                style={{
                  left: '35%',
                  top: '31.67%',
                  width: '37.5%',
                  height: '35%'
                }}
              />

              {/* 5.2 Layer 4: Skyline (India Gate) Layer with Parallax */}
              <div
                ref={skylineRef}
                className="absolute pointer-events-none"
                style={{
                  left: '29.4%',
                  top: '81.1%',
                  width: '41.9%',
                  height: '18.9%'
                }}
              />

              {/* 5.5 Orbit Lines SVG Overlay (viewBox 0 0 1600 900) */}
              <svg
                ref={orbitRef}
                viewBox="0 0 1600 900"
                className="absolute inset-0 w-full h-full pointer-events-none"
              >
                {/* Ellipse A around Hourglass: centre (805, 452), rx=330, ry=118, rotated -6 deg */}
                <ellipse
                  className="orbit-path"
                  cx="805"
                  cy="452"
                  rx="330"
                  ry="118"
                  transform="rotate(-6 805 452)"
                  fill="none"
                  stroke="#C69A55"
                  strokeWidth="1.2"
                  pathLength={1}
                  strokeDasharray={1}
                />

                {/* Ellipse B (Large): rx=600, ry=190, rotated +4 deg, 60% opacity */}
                <ellipse
                  className="orbit-path"
                  cx="805"
                  cy="452"
                  rx="600"
                  ry="190"
                  transform="rotate(4 805 452)"
                  fill="none"
                  stroke="#C69A55"
                  strokeOpacity="0.60"
                  strokeWidth="1.2"
                  pathLength={1}
                  strokeDasharray={1}
                />

                {/* Ellipse C (Dotted 2 8): rx=470, ry=150, rotated -3 deg, 50% opacity */}
                <ellipse
                  className="orbit-path"
                  cx="805"
                  cy="452"
                  rx="470"
                  ry="150"
                  transform="rotate(-3 805 452)"
                  fill="none"
                  stroke="#C69A55"
                  strokeOpacity="0.50"
                  strokeDasharray="2 8"
                  strokeWidth="1"
                  pathLength={1}
                />

                {/* Hero Constellation (26 seeded dots, Seed 5) */}
                {heroConstellation.map((pt, idx) => (
                  <circle
                    key={idx}
                    cx={pt.x}
                    cy={pt.y}
                    r={pt.r}
                    fill="#C69A55"
                    fillOpacity="0.50"
                  />
                ))}

                {/* 6 Travelling Dots Riding Ellipse B */}
                {travellingDots.map((dot, idx) => (
                  <g key={`travelling-${idx}`}>
                    <circle cx={dot.x} cy={dot.y} r={5} fill="#C69A55" />
                    <circle cx={dot.x} cy={dot.y} r={9} fill="none" stroke="#C69A55" strokeOpacity="0.3" strokeWidth="1" />
                  </g>
                ))}

                {/* Falling Sand in Hourglass Neck (y: 430 -> 500) */}
                {fallingSand.map((sand, idx) => (
                  <circle
                    key={`sand-${idx}`}
                    cx={805}
                    cy={sand.y}
                    r={2.2}
                    fill="#C69A55"
                    fillOpacity={sand.opacity}
                  />
                ))}
              </svg>

              {/* 5.3 Side Labels (Humanity vs Computation) */}
              <div
                className="absolute top-[8%] left-[4%] pointer-events-none font-mono text-[10px] tracking-[0.25em] transition-opacity duration-300"
                style={{
                  color: '#433A32',
                  opacity: mouseSide === 'left' ? 1.0 : 0.4
                }}
              >
                HUMANITY • JUDGEMENT • OBSERVATION
              </div>
              <div
                className="absolute top-[8%] right-[4%] pointer-events-none font-mono text-[10px] tracking-[0.25em] transition-opacity duration-300"
                style={{
                  color: '#433A32',
                  opacity: mouseSide === 'right' ? 1.0 : 0.4
                }}
              >
                COMPUTATION • PATTERNS • TIME
              </div>

              {/* 5.3 Real Typography Stack inside Stage */}
              {/* KRONOS Wordmark with Centered Clock-Dial O */}
              <div
                className="absolute w-full flex items-center justify-center"
                style={{ top: '9.2%' }}
              >
                <h1
                  ref={wordmarkRef}
                  className="font-serif font-bold text-[#30251F] flex items-center justify-center tracking-[0.06em]"
                  style={{ fontSize: '7.4cqw', lineHeight: 1 }}
                >
                  <span>KR</span>
                  {/* 5.4 Clock-Dial O (SVG 100x100) */}
                  <span className="inline-flex items-center justify-center mx-[0.04em]">
                    <svg
                      ref={dialRef}
                      viewBox="0 0 100 100"
                      className="w-[0.78em] h-[0.78em] overflow-visible"
                      aria-label="Clock Dial O"
                    >
                      {/* Outer circle r=46 (stroke 3) */}
                      <circle cx="50" cy="50" r="46" fill="none" stroke="#A86F45" strokeWidth="3" />
                      {/* Inner circle r=38 (stroke 1) */}
                      <circle cx="50" cy="50" r="38" fill="none" stroke="#A86F45" strokeWidth="1" />
                      {/* 12 Ticks turning slowly with animation: spin 60s linear infinite */}
                      <g className="animate-spin-slow origin-center">
                        {[...Array(12)].map((_, i) => {
                          const angle = i * 30;
                          const isMajor = i % 3 === 0;
                          const len = isMajor ? 15 : 11;
                          return (
                            <line
                              key={i}
                              x1="50"
                              y1={50 - 46}
                              x2="50"
                              y2={50 - 46 + len}
                              stroke="#A86F45"
                              strokeWidth={isMajor ? 2 : 1}
                              transform={`rotate(${angle} 50 50)`}
                            />
                          );
                        })}
                      </g>
                      {/* Crosshair */}
                      <line x1="50" y1="18" x2="50" y2="82" stroke="#A86F45" strokeWidth="1" strokeOpacity="0.6" />
                      <line x1="18" y1="50" x2="82" y2="50" stroke="#A86F45" strokeWidth="1" strokeOpacity="0.6" />
                      {/* Terracotta Center Dot */}
                      <circle cx="50" cy="50" r="3.2" fill="#B96D50" />
                    </svg>
                  </span>
                  <span>NOS</span>
                </h1>
              </div>

              {/* Headline */}
              <p
                ref={headlineRef}
                className="absolute w-full text-center font-mono font-medium text-[#433A32] uppercase tracking-[0.3em]"
                style={{ top: '25.3%', fontSize: 'max(11px, 1.65cqw)' }}
              >
                CONNECTING EVIDENCE.<br />
                RECONSTRUCTING TRUTH.
              </p>

              {/* Supporting Line */}
              <p
                ref={supportRef}
                className="absolute w-full text-center font-serif italic text-[#30251F]"
                style={{ top: '66.3%', fontSize: 'max(11px, 1.45cqw)' }}
              >
                An intelligent investigation environment connecting people, events, evidence and time.
              </p>

              {/* Action Buttons */}
              <div
                ref={ctaGroupRef}
                className="absolute w-full flex items-center justify-center gap-4 z-10"
                style={{ top: '75.2%' }}
              >
                <button
                  onClick={onEnterDashboard}
                  className="px-6 py-3 rounded-full bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] font-sans font-medium text-xs md:text-sm tracking-wide shadow-md hover:-translate-y-0.5 hover:shadow-copper transition-all flex items-center gap-2"
                >
                  <span>ENTER KRONOS</span>
                  <ArrowRight className="w-4 h-4" />
                </button>

                <button
                  onClick={onExplorePerson}
                  className="px-6 py-3 rounded-full border border-[#A86F45] text-[#30251F] hover:bg-[#F8F3E9]/80 font-sans font-medium text-xs md:text-sm tracking-wide hover:-translate-y-0.5 transition-all"
                >
                  EXPLORE THE INTELLIGENCE NETWORK
                </button>
              </div>
            </div>
          </div>

          {/* 13. The SCROLL Cue Button */}
          <button
            ref={scrollCueRef}
            onClick={handleScrollCueClick}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-[8] flex flex-col items-center gap-1 text-[#433A32] font-mono text-[10px] tracking-[0.2em] transition-opacity duration-300"
          >
            <span>SCROLL</span>
            <div className="animate-bob">
              <ArrowDown className="w-3.5 h-3.5 text-[#B96D50]" />
            </div>
          </button>
        </div>
      </div>

      {/* 8. The Numbered Story Sections (Below Hero) */}
      <div className="relative z-10 max-w-[1100px] mx-auto px-6 py-28 space-y-[14vh] text-[#30251F]">
        {/* Story Section 01 */}
        <section className="story-block space-y-6">
          <div className="font-mono text-xs uppercase tracking-[0.25em] text-[#B96D50] font-semibold">
            01 • THE IDEA
          </div>
          <h2 className="font-serif text-3xl md:text-5xl font-normal leading-tight">
            HUMAN <span className="italic text-[#B96D50]">+ machine</span>
          </h2>
          <p className="font-serif text-lg md:text-2xl text-[#433A32] leading-relaxed max-w-3xl">
            Modern syndicates exploit fragmented jurisdictions, burner identities, and high-velocity mule networks. KRONOS bridges human deductive intuition with machine scale.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8">
            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h3 className="font-mono text-xs uppercase tracking-wider text-[#A86F45] font-semibold">
                HUMAN — THE JUDGEMENT THAT QUESTIONS
              </h3>
              <p className="text-sm text-[#433A32]/85 leading-relaxed font-sans">
                Formulating hypotheses, assessing suspect intent, conducting interrogation strategy, and upholding constitutional evidentiary standards.
              </p>
            </div>

            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h3 className="font-mono text-xs uppercase tracking-wider text-[#A86F45] font-semibold">
                AI — THE INTELLIGENCE THAT CONNECTS
              </h3>
              <p className="text-sm text-[#433A32]/85 leading-relaxed font-sans">
                Correlating multimodal CDR pings, banking transactions, cross-state FIR filings, and temporal rendezvous in seconds.
              </p>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-[#FAF6F0] border border-[#DCCAB0] font-mono text-xs text-center text-[#B96D50] tracking-wider font-semibold">
            HUMAN + AI + EVIDENCE = KRONOS
          </div>
        </section>

        {/* Story Section 02 - HUMAN */}
        <section className="story-block space-y-6">
          <div className="font-mono text-xs uppercase tracking-[0.25em] text-[#B96D50] font-semibold">
            02 • HUMAN
          </div>
          <h2 className="font-serif text-3xl md:text-5xl font-normal leading-tight">
            What is <span className="italic text-[#B96D50]">observed</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Observation</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Ground-truth surveillance, physical recoveries, witness statements, and crime scene forensics logged with cryptographic timestamps.
              </p>
            </div>

            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Judgement</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Experienced investigators discerning deceptive alibis, circumstantial anomalies, and cross-border conspiracy motives.
              </p>
            </div>

            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Accountability</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Every investigative finding is rooted strictly in demonstrable records, preserving chain of custody for court presentation.
              </p>
            </div>
          </div>
        </section>

        {/* Story Section 02 - AI */}
        <section className="story-block space-y-6">
          <div className="font-mono text-xs uppercase tracking-[0.25em] text-[#B96D50] font-semibold">
            02 • AI
          </div>
          <h2 className="font-serif text-3xl md:text-5xl font-normal leading-tight">
            What is <span className="italic text-[#A86F45]">connected</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Records</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Ingesting telecommunications CDR logs, RTGS/NEFT transaction trails, and interstate FIR dockets into one unified graph.
              </p>
            </div>

            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Patterns</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Uncovering hidden shell entities, co-location clusters, burner SIM swap intervals, and anomalous financial volume spikes.
              </p>
            </div>

            <div className="border-t border-[#A86F45]/30 pt-4 space-y-2">
              <h4 className="font-serif text-lg font-bold text-[#30251F]">Time</h4>
              <p className="text-xs text-[#433A32]/85 leading-relaxed">
                Reconstructing microsecond-accurate chronology so disparate events across multiple police stations align into one coherent narrative.
              </p>
            </div>
          </div>
        </section>

        {/* Story Section 03 - ENTER */}
        <section className="story-block text-center space-y-8 pt-10">
          <div className="font-mono text-xs uppercase tracking-[0.25em] text-[#B96D50] font-semibold">
            03 • ENTER
          </div>
          <h2 className="font-serif text-3xl md:text-6xl font-normal max-w-2xl mx-auto leading-tight">
            Meet at the intersection of <span className="italic text-[#B96D50]">evidence</span> and <span className="italic text-[#A86F45]">time</span>.
          </h2>

          <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
            <button
              onClick={onExplorePerson}
              className="px-6 py-3 rounded-full bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] font-sans font-medium text-xs md:text-sm tracking-wide shadow-md transition-all flex items-center gap-2"
            >
              <span>INSPECT SUSPECT DOSSIER (P-0427)</span>
              <ArrowRight className="w-4 h-4" />
            </button>

            <button
              onClick={onEnterDashboard}
              className="px-6 py-3 rounded-full border border-[#30251F] text-[#30251F] hover:bg-[#30251F] hover:text-[#F8F3E9] font-sans font-medium text-xs md:text-sm tracking-wide transition-all"
            >
              OPEN INVESTIGATIVE DASHBOARD
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

