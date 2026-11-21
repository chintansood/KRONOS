import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { 
  Network, 
  ZoomIn, 
  ZoomOut, 
  RotateCcw, 
  Filter, 
  Search, 
  User, 
  FolderKanban, 
  Phone, 
  CreditCard, 
  MapPin, 
  FileText,
  ArrowRight,
  Info,
  Maximize2
} from 'lucide-react';
import { GraphNode, GraphEdge } from '../types/investigation';
import { MOCK_GRAPH_NODES, MOCK_GRAPH_EDGES } from '../data/mockData';

interface ThreeRelationshipGraphProps {
  initialFocusId?: string;
  onOpenPerson: (personId: string) => void;
  onOpenCase: (caseId: string) => void;
  onOpenEvidence: (evidenceId: string) => void;
  onBack?: () => void;
}

export const ThreeRelationshipGraph: React.FC<ThreeRelationshipGraphProps> = ({
  initialFocusId = 'P-0427',
  onOpenPerson,
  onOpenCase,
  onOpenEvidence,
  onBack
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [filterType, setFilterType] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRotate, setAutoRotate] = useState(true);

  // Filtered nodes & edges
  const filteredNodes = MOCK_GRAPH_NODES.filter(node => {
    const matchesType = filterType === 'ALL' || node.type === filterType;
    const matchesSearch = !searchQuery || 
      node.label.toLowerCase().includes(searchQuery.toLowerCase()) || 
      node.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (node.sublabel && node.sublabel.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesType && matchesSearch;
  });

  const nodeMap = new Map<string, GraphNode>();
  filteredNodes.forEach(n => nodeMap.set(n.id, n));

  const filteredEdges = MOCK_GRAPH_EDGES.filter(edge => 
    nodeMap.has(edge.source) && nodeMap.has(edge.target)
  );

  // Colors mapping for warm editorial design
  const typeColors: Record<string, number> = {
    PERSON: 0xB96D50,    // Terracotta
    CASE: 0xC69A55,      // Antique gold
    DEVICE: 0x7B8062,    // Muted olive
    ACCOUNT: 0xA86F45,   // Burnished copper
    LOCATION: 0x8C7853,  // Antique bronze
    EVIDENCE: 0x433A32   // Warm charcoal
  };

  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xF5EFEB); // Warm antique ivory backdrop
    scene.fog = new THREE.FogExp2(0xF5EFEB, 0.0018);

    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000);
    camera.position.set(0, 50, 320);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // Subtle Ambient & Directional Lights
    const ambientLight = new THREE.AmbientLight(0xfff5ea, 1.4);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffecd2, 1.2);
    dirLight1.position.set(100, 150, 100);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xd9b790, 0.8);
    dirLight2.position.set(-100, -100, -50);
    scene.add(dirLight2);

    // Node 3D meshes map
    const nodeMeshes: { [id: string]: THREE.Mesh } = {};
    const group = new THREE.Group();
    scene.add(group);

    // Calculate node 3D positions with deterministic layout
    filteredNodes.forEach((node, i) => {
      const radius = node.type === 'CASE' ? 120 : node.type === 'PERSON' ? 70 : 160;
      const angle = (i / filteredNodes.length) * Math.PI * 2;
      const elevation = ((i % 5) - 2) * 35;

      const x = node.x ?? Math.cos(angle) * radius + (Math.sin(i * 1.5) * 15);
      const y = node.y ?? elevation;
      const z = node.z ?? Math.sin(angle) * radius;

      // Base geometry sizing
      const size = node.val ? Math.max(4, node.val * 0.9) : 6;
      const geom = new THREE.SphereGeometry(size, 24, 24);
      const colorHex = typeColors[node.type] || 0xA86F45;
      
      const mat = new THREE.MeshStandardMaterial({
        color: colorHex,
        roughness: 0.35,
        metalness: 0.25,
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.set(x, y, z);
      mesh.userData = { node };
      group.add(mesh);
      nodeMeshes[node.id] = mesh;

      // Orbital halo ring for key suspect Rohan Mehta & CASE-014
      if (node.id === 'P-0427' || node.id === 'CASE-014') {
        const ringGeom = new THREE.RingGeometry(size * 1.4, size * 1.65, 32);
        const ringMat = new THREE.MeshBasicMaterial({ 
          color: 0xC69A55, 
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.65 
        });
        const ring = new THREE.Mesh(ringGeom, ringMat);
        ring.rotation.x = Math.PI / 2;
        mesh.add(ring);
      }
    });

    // Edges Line geometry
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0xBAA48A,
      transparent: true,
      opacity: 0.45,
      linewidth: 1
    });

    const alertLineMaterial = new THREE.LineBasicMaterial({
      color: 0xB96D50,
      transparent: true,
      opacity: 0.85,
      linewidth: 2
    });

    filteredEdges.forEach(edge => {
      const sourceMesh = nodeMeshes[edge.source];
      const targetMesh = nodeMeshes[edge.target];
      if (!sourceMesh || !targetMesh) return;

      const points = [sourceMesh.position, targetMesh.position];
      const lineGeom = new THREE.BufferGeometry().setFromPoints(points);
      const line = new THREE.Line(lineGeom, edge.isAnomaly ? alertLineMaterial : lineMaterial);
      group.add(line);
    });

    // Raycaster for hover/clicks
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    // Mouse drag interaction state
    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };

    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / height) * 2 + 1;

      if (isDragging) {
        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;
        group.rotation.y += deltaX * 0.005;
        group.rotation.x += deltaY * 0.005;
        previousMousePosition = { x: e.clientX, y: e.clientY };
      } else {
        // Raycasting check
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(Object.values(nodeMeshes));
        if (intersects.length > 0) {
          const hit = intersects[0].object.userData.node as GraphNode;
          setHoveredNode(hit);
          container.style.cursor = 'pointer';
        } else {
          setHoveredNode(null);
          container.style.cursor = 'grab';
        }
      }
    };

    const onMouseUp = () => {
      isDragging = false;
    };

    const onClick = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(Object.values(nodeMeshes));
      if (intersects.length > 0) {
        const hit = intersects[0].object.userData.node as GraphNode;
        setSelectedNode(hit);
      }
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      camera.position.z = Math.max(120, Math.min(500, camera.position.z + e.deltaY * 0.25));
    };

    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    container.addEventListener('click', onClick);
    container.addEventListener('wheel', onWheel, { passive: false });

    // Initial focus on initialFocusId if present
    const initMesh = nodeMeshes[initialFocusId];
    if (initMesh) {
      setSelectedNode(initMesh.userData.node);
    }

    // Animation loop
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      if (autoRotate && !isDragging) {
        group.rotation.y += 0.0018;
      }

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      const newW = container.clientWidth;
      const newH = container.clientHeight;
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      renderer.setSize(newW, newH);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      container.removeEventListener('click', onClick);
      container.removeEventListener('wheel', onWheel);
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
    };
  }, [filterType, searchQuery, autoRotate]);

  const handleEntityDrilldown = (node: GraphNode) => {
    if (node.type === 'PERSON') {
      onOpenPerson(node.id);
    } else if (node.type === 'CASE') {
      onOpenCase(node.id);
    } else if (node.type === 'EVIDENCE') {
      onOpenEvidence(node.id);
    }
  };

  return (
    <div className="relative w-full h-[calc(100vh-68px)] bg-[#FAF6F0] overflow-hidden flex">
      {/* 3D WebGL Canvas Viewport */}
      <div 
        ref={mountRef} 
        className="w-full h-full cursor-grab active:cursor-grabbing outline-none"
      />

      {/* Floating Header & Search Bar */}
      <div className="absolute top-5 left-6 z-20 flex flex-col gap-3">
        <div className="bg-[#FBF8F3]/95 backdrop-blur-md border border-[#DCCAB0] p-4 rounded-xl shadow-md w-80">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Network className="w-5 h-5 text-[#B96D50]" />
              <h2 className="font-serif text-lg font-bold text-[#30251F]">Intelligence Topology</h2>
            </div>
            {onBack && (
              <button 
                onClick={onBack}
                className="text-xs text-[#A86F45] hover:underline uppercase tracking-wider font-mono"
              >
                Back
              </button>
            )}
          </div>
          <p className="text-xs text-[#433A32]/80 leading-relaxed mb-3">
            Interactive multi-relational network mapping CDR records, shell entities, co-conspirators, and financial corridors.
          </p>

          {/* Quick Search */}
          <div className="relative mb-3">
            <Search className="w-4 h-4 text-[#A86F45] absolute left-3 top-2.5" />
            <input 
              type="text"
              placeholder="Search node (e.g. Rohan, CASE-014)..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-[#F5EFEB] border border-[#DCCAB0] rounded-lg text-xs font-mono text-[#30251F] focus:outline-none focus:border-[#B96D50]"
            />
          </div>

          {/* Entity Type Filters */}
          <div className="flex flex-wrap gap-1.5">
            {['ALL', 'PERSON', 'CASE', 'DEVICE', 'ACCOUNT', 'EVIDENCE'].map(type => (
              <button
                key={type}
                onClick={() => setFilterType(type)}
                className={`px-2.5 py-1 rounded text-[11px] font-mono transition-all ${
                  filterType === type 
                    ? 'bg-[#30251F] text-[#F8F3E9] shadow-sm font-semibold' 
                    : 'bg-[#EFE7DC] text-[#433A32] hover:bg-[#E3D7C5]'
                }`}
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="bg-[#FBF8F3]/90 backdrop-blur-md border border-[#DCCAB0] px-4 py-2.5 rounded-lg shadow-sm w-80 text-[11px] flex flex-wrap items-center justify-between gap-2 text-[#433A32]">
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#B96D50]"></span> Person</div>
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#C69A55]"></span> Case</div>
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#7B8062]"></span> Device</div>
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#A86F45]"></span> Account</div>
          <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#433A32]"></span> Evidence</div>
        </div>
      </div>

      {/* Floating Controls Overlay (Bottom Left) */}
      <div className="absolute bottom-6 left-6 z-20 flex items-center gap-2 bg-[#FBF8F3]/95 backdrop-blur-md border border-[#DCCAB0] p-1.5 rounded-lg shadow-sm">
        <button 
          onClick={() => setAutoRotate(!autoRotate)}
          className={`px-2.5 py-1.5 rounded text-xs font-mono flex items-center gap-1.5 transition-colors ${
            autoRotate ? 'bg-[#A86F45] text-white' : 'hover:bg-[#EFE7DC] text-[#30251F]'
          }`}
          title="Toggle Auto Rotation"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>{autoRotate ? 'Rotating' : 'Paused'}</span>
        </button>
        <div className="h-4 w-px bg-[#DCCAB0]" />
        <span className="text-[11px] text-[#7B8062] px-2 font-mono">
          Drag to orbit • Scroll to zoom
        </span>
      </div>

      {/* Floating Hover Card (Near cursor/center top) */}
      {hoveredNode && !selectedNode && (
        <div className="absolute top-6 right-6 z-20 pointer-events-none bg-[#30251F]/90 text-[#F8F3E9] p-3 rounded-lg shadow-xl backdrop-blur border border-[#C69A55]/30 max-w-xs animate-fade-in">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#C69A55]/20 text-[#C69A55] border border-[#C69A55]/30">
              {hoveredNode.type}
            </span>
            <span className="font-mono text-xs text-[#DCCAB0]">{hoveredNode.id}</span>
          </div>
          <div className="font-serif text-sm font-bold text-[#F8F3E9]">{hoveredNode.label}</div>
          {hoveredNode.sublabel && (
            <div className="text-xs text-[#DCCAB0]/80 mt-0.5">{hoveredNode.sublabel}</div>
          )}
          <div className="text-[10px] text-[#A86F45] mt-2 font-mono flex items-center gap-1">
            <span>Click to inspect metadata</span>
          </div>
        </div>
      )}

      {/* Selected Node Detailed Inspector Sidebar (Right Side) */}
      {selectedNode && (
        <div className="absolute top-5 right-6 bottom-6 w-96 bg-[#FBF8F3]/95 backdrop-blur-md border border-[#DCCAB0] rounded-xl shadow-2xl z-20 flex flex-col animate-slide-left overflow-hidden">
          {/* Header */}
          <div className="p-5 border-b border-[#DCCAB0] bg-[#F5EFEB]/80 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[10px] font-mono uppercase tracking-widest px-2 py-0.5 rounded bg-[#A86F45]/15 text-[#A86F45] border border-[#A86F45]/30 font-bold">
                  {selectedNode.type}
                </span>
                <span className="font-mono text-xs text-[#433A32]/70 font-semibold">{selectedNode.id}</span>
              </div>
              <h3 className="font-serif text-xl font-bold text-[#30251F]">{selectedNode.label}</h3>
              {selectedNode.sublabel && (
                <p className="text-xs text-[#A86F45] font-medium mt-0.5">{selectedNode.sublabel}</p>
              )}
            </div>
            <button 
              onClick={() => setSelectedNode(null)}
              className="p-1 rounded hover:bg-[#EAE0D2] text-[#433A32]"
              title="Close Panel"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Details Body */}
          <div className="p-5 space-y-5 overflow-y-auto flex-1 font-sans text-xs text-[#433A32]">
            {/* Metric Chips */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-[#F5EFEB] rounded-lg border border-[#DCCAB0]">
                <div className="text-[10px] uppercase font-mono text-[#A86F45] mb-1">Graph Degree</div>
                <div className="font-serif text-lg font-bold text-[#30251F]">
                  {filteredEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length} Links
                </div>
              </div>
              <div className="p-3 bg-[#F5EFEB] rounded-lg border border-[#DCCAB0]">
                <div className="text-[10px] uppercase font-mono text-[#A86F45] mb-1">Centrality Weight</div>
                <div className="font-serif text-lg font-bold text-[#B96D50]">
                  {selectedNode.val ? `${selectedNode.val * 10}%` : '65%'}
                </div>
              </div>
            </div>

            {/* Direct Connected Relationships */}
            <div>
              <h4 className="font-mono uppercase text-[11px] tracking-wider text-[#A86F45] mb-2 font-semibold">
                Direct Connected Entities
              </h4>
              <div className="space-y-2">
                {filteredEdges
                  .filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
                  .slice(0, 6)
                  .map((e, idx) => {
                    const peerId = e.source === selectedNode.id ? e.target : e.source;
                    const peerNode = nodeMap.get(peerId);
                    return (
                      <div 
                        key={idx}
                        onClick={() => peerNode && setSelectedNode(peerNode)}
                        className="p-2.5 bg-[#FAF6F0] rounded-lg border border-[#DCCAB0]/70 hover:border-[#B96D50] hover:bg-[#F5EFEB] cursor-pointer transition-all flex items-center justify-between"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[10px] text-[#A86F45]">{peerId}</span>
                            <span className="font-medium text-xs text-[#30251F]">{peerNode?.label || peerId}</span>
                          </div>
                          {e.label && (
                            <div className="text-[10px] text-[#433A32]/70 mt-0.5">{e.label}</div>
                          )}
                        </div>
                        {e.isAnomaly && (
                          <span className="text-[9px] font-mono text-[#B96D50] uppercase font-bold bg-[#B96D50]/10 px-1.5 py-0.5 rounded">
                            Anomaly
                          </span>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>

            {/* Investigative Summary */}
            <div className="p-3 bg-[#FAF6F0] rounded-lg border border-[#DCCAB0] text-xs leading-relaxed text-[#433A32]/90">
              <div className="flex items-center gap-1.5 text-[#B96D50] font-medium mb-1">
                <Info className="w-3.5 h-3.5" />
                <span>Analytical Context</span>
              </div>
              {selectedNode.type === 'PERSON' && (
                <p>Identified across multiple financial transfer paths and burner communication clusters. High degree of topological influence in regional operations.</p>
              )}
              {selectedNode.type === 'CASE' && (
                <p>Active multi-jurisdictional FIR record linked to 6 cross-case suspect records with active physical surveillance logs.</p>
              )}
              {selectedNode.type === 'DEVICE' && (
                <p>Hardware IMEI identified connecting 2 separate burner SIM profiles registered under altered KYC documents.</p>
              )}
              {selectedNode.type === 'ACCOUNT' && (
                <p>Mule banking node routing layered transactions exceeding ₹45,00,000 within 72 hours of primary FIR registration.</p>
              )}
              {selectedNode.type === 'EVIDENCE' && (
                <p>Cryptographically validated evidence record with high chain-of-custody integrity.</p>
              )}
            </div>
          </div>

          {/* Action Footer */}
          <div className="p-4 border-t border-[#DCCAB0] bg-[#F5EFEB]/90">
            {(selectedNode.type === 'PERSON' || selectedNode.type === 'CASE' || selectedNode.type === 'EVIDENCE') ? (
              <button
                onClick={() => handleEntityDrilldown(selectedNode)}
                className="w-full py-2.5 px-4 bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] rounded-lg font-serif text-sm font-semibold tracking-wide shadow transition-colors flex items-center justify-center gap-2"
              >
                <span>
                  {selectedNode.type === 'PERSON' ? 'Open Suspect Dossier' : selectedNode.type === 'CASE' ? 'Open Case Workspace' : 'Inspect Evidence'}
                </span>
                <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <div className="text-center font-mono text-xs text-[#7B8062]">
                Terminal entity node • Associated with active investigation
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

