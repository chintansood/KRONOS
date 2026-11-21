import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Compass, Shield, Clock, FileText, MapPin, DollarSign, Fingerprint, Users, Eye } from 'lucide-react';

interface HeroSectionProps {
  onEnterDashboard: () => void;
  onExploreNetwork: () => void;
  onSelectEvidenceSnippet?: (type: string) => void;
}

export const HeroSection: React.FC<HeroSectionProps> = ({
  onEnterDashboard,
  onExploreNetwork,
  onSelectEvidenceSnippet
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [activeOrbitalSnippet, setActiveOrbitalSnippet] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Interactive subtle particle flow through hourglass center and orbital lines
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.parentElement?.clientWidth || window.innerWidth);
    let height = (canvas.height = canvas.parentElement?.clientHeight || window.innerHeight);

    const handleResize = () => {
      if (!canvas.parentElement) return;
      width = canvas.width = canvas.parentElement.clientWidth;
      height = canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener('resize', handleResize);

    // Particles representing temporal intelligence flowing into the center
    const particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;
      alpha: number;
      orbitAngle: number;
      orbitSpeed: number;
      orbitRadiusX: number;
      orbitRadiusY: number;
      color: string;
    }> = [];

    const colors = ['#C69A55', '#B96D50', '#A86F45', '#DCCAB0'];
    const centerX = width / 2;
    const centerY = height * 0.48;

    for (let i = 0; i < 45; i++) {
      particles.push({
        x: centerX + (Math.random() - 0.5) * 200,
        y: centerY + (Math.random() - 0.5) * 160,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() * 0.4 + 0.2), // gentle downward sand flow
        radius: Math.random() * 1.8 + 0.6,
        alpha: Math.random() * 0.7 + 0.3,
        orbitAngle: Math.random() * Math.PI * 2,
        orbitSpeed: (Math.random() * 0.008 + 0.003) * (Math.random() > 0.5 ? 1 : -1),
        orbitRadiusX: 180 + Math.random() * 80,
        orbitRadiusY: 60 + Math.random() * 30,
        color: colors[Math.floor(Math.random() * colors.length)]
      });
    }

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // Draw delicate elliptical orbital path
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(centerX, centerY, 210, 75, -0.05, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(198, 154, 85, 0.22)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 6]);
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(centerX, centerY, 260, 95, 0.08, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(185, 109, 80, 0.16)';
      ctx.lineWidth = 0.8;
      ctx.setLineDash([2, 8]);
      ctx.stroke();
      ctx.restore();

      // Update & render flowing particles
      particles.forEach((p, idx) => {
        // Some particles follow the orbital ring
        if (idx % 2 === 0) {
          p.orbitAngle += p.orbitSpeed;
          p.x = centerX + Math.cos(p.orbitAngle) * p.orbitRadiusX;
          p.y = centerY + Math.sin(p.orbitAngle) * p.orbitRadiusY;
        } else {
          // Others flow through the central hourglass stem
          p.y += p.vy;
          p.x += Math.sin(p.y * 0.05) * 0.4;
          if (p.y > centerY + 80) {
            p.y = centerY - 80;
            p.x = centerX + (Math.random() - 0.5) * 40;
          }
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha;
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const { clientX, clientY, currentTarget } = e;
    const { width, height, left, top } = currentTarget.getBoundingClientRect();
    const x = ((clientX - left) / width - 0.5) * 14;
    const y = ((clientY - top) / height - 0.5) * 14;
    setMousePos({ x, y });
  };

  const orbitalEvidenceNodes = [
    { id: 'FIR', label: 'FIR 2025/14', icon: FileText, x: '24%', y: '44%', tooltip: 'Registered Case Docket: Financial Fraud' },
    { id: 'LOCATION', label: 'GPS 30.73° N', icon: MapPin, x: '35%', y: '36%', tooltip: 'Location Ping: Sector 17 Rendezvous' },
    { id: 'FINANCIAL', label: 'RTGS ₹4.85L', icon: DollarSign, x: '50%', y: '58%', tooltip: 'Core Banking Flow: Layer Two Dispersal' },
    { id: 'COMMUNICATION', label: 'Telegram Archive', icon: Eye, x: '66%', y: '38%', tooltip: 'Encrypted Broadcast: Consignment Ledger' },
    { id: 'IDENTITY', label: 'Suspect Cluster', icon: Users, x: '75%', y: '46%', tooltip: 'Entity Cross-Correlation: 11 Accused' },
    { id: 'FORENSICS', label: 'Handset DEV-PX', icon: Fingerprint, x: '60%', y: '62%', tooltip: 'Hardware Lineage: Cloned IMEI Detection' },
  ];

  return (
    <section 
      onMouseMove={handleMouseMove}
      className="relative min-h-[calc(100vh-73px)] w-full flex flex-col justify-between overflow-hidden bg-parchment-light border-b border-delicate select-none"
    >
      {/* Background Architectural Artwork & Reference Composition */}
      <div 
        className="absolute inset-0 pointer-events-none transition-transform duration-300 ease-out"
        style={{
          transform: `translate3d(${mousePos.x * 0.4}px, ${mousePos.y * 0.4}px, 0)`
        }}
      >
        <img 
          src="/assets/kronos-hero-artwork.jpg" 
          alt="KRONOS Investigation: Human Investigator, Central Golden Hourglass, and Humanoid AI" 
          className="w-full h-full object-cover object-center opacity-85 mix-blend-multiply filter contrast-[1.04] brightness-[0.98]"
        />
        {/* Warm sepia gradient overlay for seamless readability */}
        <div className="absolute inset-0 bg-gradient-to-t from-parchment-light via-transparent to-parchment-light/40"></div>
        <div className="absolute inset-0 bg-radial from-transparent via-parchment-light/10 to-parchment/60"></div>
      </div>

      {/* Dynamic Canvas Particles for Golden Hourglass & Orbital Evidence */}
      <canvas 
        ref={canvasRef} 
        className="absolute inset-0 pointer-events-none z-10"
      />

      {/* Interactive Orbital Hotspots over the Central Composition */}
      <div className="absolute inset-0 z-20 pointer-events-none">
        {orbitalEvidenceNodes.map((node) => {
          const Icon = node.icon;
          const isHovered = activeOrbitalSnippet === node.id;
          return (
            <div
              key={node.id}
              style={{ left: node.x, top: node.y }}
              className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-auto group"
              onMouseEnter={() => setActiveOrbitalSnippet(node.id)}
              onMouseLeave={() => setActiveOrbitalSnippet(null)}
              onClick={() => onSelectEvidenceSnippet?.(node.id)}
            >
              <div className={`p-2 rounded-full border backdrop-blur-md transition-all duration-300 cursor-pointer shadow-warm flex items-center space-x-1.5 ${
                isHovered 
                  ? 'bg-espresso text-parchment border-gold scale-110 shadow-copper' 
                  : 'bg-parchment-light/80 text-espresso border-copper/30 hover:border-terracotta hover:scale-105'
              }`}>
                <Icon className="w-3.5 h-3.5 text-copper" />
                <span className="font-mono text-[10px] font-semibold tracking-wider uppercase pr-1 hidden sm:inline">
                  {node.label}
                </span>
              </div>

              {/* Tooltip Popup on Hover */}
              {isHovered && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2.5 rounded-lg bg-espresso text-parchment-light text-[11px] font-sans shadow-warm-lg border border-copper/40 z-30 pointer-events-none animate-in fade-in zoom-in-95">
                  <span className="font-mono text-[9px] uppercase tracking-widest text-gold block mb-1">
                    Verified Digital Evidence
                  </span>
                  <p>{node.tooltip}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Top Hero Brand Header Typography */}
      <div className="relative z-20 pt-8 sm:pt-12 text-center max-w-4xl mx-auto px-4">
        {/* Circular Crosshair Logo Glyph & K R O N O S Wordmark */}
        <div className="flex items-center justify-center space-x-2 sm:space-x-3 mb-3">
          <span className="font-serif tracking-[0.35em] text-3xl sm:text-5xl lg:text-6xl font-black text-espresso">
            K R O N O S
          </span>
        </div>

        {/* Primary Headline */}
        <h1 className="font-serif tracking-[0.18em] text-sm sm:text-lg lg:text-xl font-bold text-copper uppercase mb-2">
          CONNECTING EVIDENCE. RECONSTRUCTING TRUTH.
        </h1>

        {/* Supporting Copy */}
        <p className="font-sans text-xs sm:text-sm text-charcoal/80 max-w-xl mx-auto tracking-wide font-medium leading-relaxed">
          An intelligent investigation environment connecting people, events, evidence and time.
        </p>
      </div>

      {/* Bottom Hero Call-to-Actions and Mode Switchers */}
      <div className="relative z-20 pb-8 sm:pb-12 text-center px-4 flex flex-col sm:flex-row items-center justify-center gap-4">
        {/* Primary Action Button: Enter Kronos */}
        <button
          onClick={onEnterDashboard}
          className="group px-7 py-3 rounded-full bg-terracotta hover:bg-terracotta-dark text-white font-serif tracking-[0.15em] text-xs uppercase shadow-warm hover:shadow-copper flex items-center space-x-3 transition-all duration-300 transform hover:-translate-y-0.5 active:translate-y-0"
        >
          <span>ENTER KRONOS</span>
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </button>

        {/* Secondary Action Button: Explore 3D Intelligence Network */}
        <button
          onClick={onExploreNetwork}
          className="group px-7 py-3 rounded-full bg-parchment-light/90 hover:bg-parchment-light text-espresso border border-copper/50 hover:border-espresso font-serif tracking-[0.15em] text-xs uppercase shadow-sm hover:shadow-warm flex items-center space-x-3 transition-all duration-300 transform hover:-translate-y-0.5"
        >
          <Compass className="w-4 h-4 text-copper group-hover:rotate-45 transition-transform" />
          <span>EXPLORE THE INTELLIGENCE NETWORK</span>
        </button>
      </div>

      {/* Subtle Archival Metadata Ribbon at bottom */}
      <div className="relative z-20 w-full border-t border-delicate bg-parchment-light/60 backdrop-blur-xs py-2 px-6 flex flex-wrap items-center justify-between text-[11px] font-mono text-charcoal/70">
        <div className="flex items-center space-x-3">
          <span className="flex items-center space-x-1">
            <Shield className="w-3.5 h-3.5 text-copper" />
            <span>LAW ENFORCEMENT DEMONSTRATION</span>
          </span>
          <span className="hidden md:inline">•</span>
          <span className="hidden md:inline">BENCHMARK: SIH-26189 CRIMINAL NETWORK ANALYSIS</span>
        </div>
        <div className="flex items-center space-x-3">
          <span>TEMPORAL ENGINE: KRONOS-V1</span>
          <span>•</span>
          <span className="text-terracotta font-semibold">51,000 RECORDS UNIFIED</span>
        </div>
      </div>
    </section>
  );
};

