import React, { useMemo } from 'react';

// Park-Miller LCG Pseudo-Random Number Generator:
// next = (current * 16807) % 2147483647
class ParkMiller {
  private state: number;
  constructor(seed: number) {
    this.state = seed;
  }
  next(): number {
    this.state = (this.state * 16807) % 2147483647;
    return this.state / 2147483647;
  }
}

interface Dot {
  x: number;
  y: number;
  r: number;
}

interface Line {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export const ArchivalBackground: React.FC = () => {
  // Generate seeded constellation (Seed 11, exactly 48 dots)
  const { dots, lines } = useMemo(() => {
    const rng = new ParkMiller(11);
    const generatedDots: Dot[] = [];
    const maxDist = 1600 * 0.20; // 20% of page width = 320px

    for (let i = 0; i < 48; i++) {
      generatedDots.push({
        x: rng.next() * 1600,
        y: rng.next() * 900,
        r: 1.5 + rng.next() * 3.0 // Radius 1.5 to 4.5
      });
    }

    const generatedLines: Line[] = [];
    const connectedPairs = new Set<string>();

    generatedDots.forEach((dot, idx) => {
      // Find distances to all other dots
      const distances: { targetIdx: number; dist: number }[] = [];
      generatedDots.forEach((otherDot, oIdx) => {
        if (idx !== oIdx) {
          const dx = dot.x - otherDot.x;
          const dy = dot.y - otherDot.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          distances.push({ targetIdx: oIdx, dist });
        }
      });

      // Sort to find 2 nearest neighbours
      distances.sort((a, b) => a.dist - b.dist);
      const nearestTwo = distances.slice(0, 2);

      nearestTwo.forEach(n => {
        if (n.dist <= maxDist) {
          const pairKey = idx < n.targetIdx ? `${idx}-${n.targetIdx}` : `${n.targetIdx}-${idx}`;
          if (!connectedPairs.has(pairKey)) {
            connectedPairs.add(pairKey);
            generatedLines.push({
              x1: dot.x,
              y1: dot.y,
              x2: generatedDots[n.targetIdx].x,
              y2: generatedDots[n.targetIdx].y
            });
          }
        }
      });
    });

    return { dots: generatedDots, lines: generatedLines };
  }, []);

  return (
    <svg
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMid slice"
      className="fixed inset-0 w-full h-full pointer-events-none z-0"
      style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }}
      aria-hidden="true"
    >
      <defs>
        {/* Layer 3.1: Paper grain using feTurbulence */}
        <filter id="kronos-paper-grain" x="0%" y="0%" width="100%" height="100%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8"
            numOctaves="2"
            result="noise"
          />
          <feColorMatrix
            type="matrix"
            values="0.2 0 0 0 0.19
                    0 0.15 0 0 0.15
                    0 0 0.12 0 0.12
                    0 0 0 0.09 0"
          />
        </filter>

        {/* Layer 3.2: Diamond lattice (Jaali pattern, 64x64px tile) */}
        <pattern
          id="kronos-jaali"
          width="64"
          height="64"
          patternUnits="userSpaceOnUse"
        >
          {/* Diamond outline */}
          <polygon
            points="32,0 64,32 32,64 0,32"
            fill="none"
            stroke="#C69A55"
            strokeOpacity="0.16"
            strokeWidth="1"
          />
          {/* Terracotta center dot */}
          <circle
            cx="32"
            cy="32"
            r="1.6"
            fill="#B96D50"
            fillOpacity="0.30"
          />
        </pattern>
      </defs>

      {/* Layer 3.1: Grain fill */}
      <rect width="100%" height="100%" filter="url(#kronos-paper-grain)" />

      {/* Layer 3.2: Jaali pattern fill */}
      <rect width="100%" height="100%" fill="url(#kronos-jaali)" />

      {/* Layer 3.3: Corner rings */}
      <g stroke="#C69A55" strokeOpacity="0.35" fill="none">
        {/* Top-left corner rings (cx: 0, cy: 0) */}
        <circle cx="0" cy="0" r="260" strokeDasharray="2 9" strokeWidth="1" />
        <circle cx="0" cy="0" r="380" strokeWidth="1" />

        {/* Bottom-right corner rings (cx: 1600, cy: 900) */}
        <circle cx="1600" cy="900" r="300" strokeDasharray="2 9" strokeWidth="1" />
        <circle cx="1600" cy="900" r="430" strokeWidth="1" />
      </g>

      {/* Layer 3.4: Constellation lines & dots */}
      <g stroke="#C69A55" strokeOpacity="0.40" strokeWidth="0.8">
        {lines.map((l, i) => (
          <line key={`line-${i}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
        ))}
      </g>
      <g fill="#C69A55" fillOpacity="0.40">
        {dots.map((d, i) => (
          <circle key={`dot-${i}`} cx={d.x} cy={d.y} r={d.r} />
        ))}
      </g>
    </svg>
  );
};

