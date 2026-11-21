import React, { useState, useEffect, useRef } from 'react';
import { 
  ArrowLeft, Bookmark, Network, ExternalLink, Calendar, 
  MapPin, Phone, Laptop, Play, Pause, RotateCcw, 
  Send, Sparkles, AlertCircle, FileText, ChevronDown, 
  ChevronUp, Check, Download, Layers, ShieldCheck, Star, X
} from 'lucide-react';
import { Person, TimelineEvent, ChatMessage, Modality } from '../types/investigation';
import { storageService } from '../services/storageService';
import { assistantService } from '../services/assistantService';
import { exportService } from '../services/exportService';

interface SuspectProfileProps {
  person: Person;
  timeline: TimelineEvent[];
  onBack: () => void;
  onOpenCase: (caseId: string) => void;
  onOpenEvidence: (evidenceId: string) => void;
  onViewGraph: (personId: string) => void;
}

export const SuspectProfile: React.FC<SuspectProfileProps> = ({
  person,
  timeline,
  onBack,
  onOpenCase,
  onOpenEvidence,
  onViewGraph
}) => {
  // Timeline playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeEventIndex, setActiveEventIndex] = useState<number>(0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [filterModality, setFilterModality] = useState<string>('ALL');

  // Chat bar state
  const [chatMode, setChatMode] = useState<'ASSISTANCE' | 'DETECTIVE'>('ASSISTANCE');
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // Bookmark state (using kr_bm)
  const [isBookmarked, setIsBookmarked] = useState(storageService.isBookmarked(person.id));

  // Graph drawer state
  const [isGraphDrawerOpen, setIsGraphDrawerOpen] = useState(false);

  // Toast feedback
  const [profileToast, setProfileToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setProfileToast(msg);
    setTimeout(() => setProfileToast(null), 2000);
  };

  // Refs for scrolling to event
  const timelineContainerRef = useRef<HTMLDivElement | null>(null);
  const eventRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Filtered timeline
  const filteredTimeline = timeline.filter(e => {
    if (filterModality !== 'ALL' && e.modality !== filterModality) return false;
    return true;
  });

  // Load chat history from localStorage key kr_chat_<personId>
  useEffect(() => {
    setIsBookmarked(storageService.isBookmarked(person.id));
    setActiveEventIndex(0);
    setIsPlaying(false);

    try {
      const saved = localStorage.getItem(`kr_chat_${person.id}`);
      if (saved) {
        setMessages(JSON.parse(saved));
      } else {
        setMessages([
          {
            id: 'msg-init',
            sender: 'KRONOS_AI',
            mode: 'ASSISTANCE',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            text: `[RECORDED FACTS]\nDossier active for **${person.name} (${person.id})**. Corroborated in ${person.casesMentioned.length} cases with ${timeline.length} recorded events.\nAsk about case involvement, financial routes, device pings, or switch to **KRONOS DETECTIVE** for algorithmic hypotheses.`,
            referencedCaseIds: person.casesMentioned,
            referencedPersonIds: [person.id]
          }
        ]);
      }
    } catch {
      // Fallback
    }
  }, [person.id]);

  // Persist messages to kr_chat_<personId> (last 20)
  useEffect(() => {
    if (messages.length > 0) {
      try {
        localStorage.setItem(`kr_chat_${person.id}`, JSON.stringify(messages.slice(-20)));
      } catch (e) {
        console.warn('Failed to save chat', e);
      }
    }
  }, [messages, person.id]);

  // Playback timer loop: 1x = 1600ms, 2x = 800ms, 4x = 400ms
  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;
    if (isPlaying) {
      timer = setInterval(() => {
        setActiveEventIndex(prev => {
          if (prev >= filteredTimeline.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          const next = prev + 1;
          const ev = filteredTimeline[next];
          if (ev) onOpenEvidence(ev.evidenceId);
          return next;
        });
      }, 1600 / playbackSpeed);
    }
    return () => clearInterval(timer);
  }, [isPlaying, playbackSpeed, filteredTimeline.length]);

  // Auto-scroll timeline to active event during playback
  useEffect(() => {
    const el = eventRefs.current[activeEventIndex];
    if (el && isPlaying) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeEventIndex, isPlaying]);

  // Jump to event by evidenceId
  const jumpToEvidence = (evidenceId: string) => {
    // Reset filter to ALL if needed so the event is visible
    setFilterModality('ALL');
    setTimeout(() => {
      const idx = timeline.findIndex(e => e.evidenceId.toLowerCase() === evidenceId.toLowerCase());
      if (idx >= 0) {
        setActiveEventIndex(idx);
        const el = eventRefs.current[idx];
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        onOpenEvidence(evidenceId);
      } else {
        onOpenEvidence(evidenceId);
      }
    }, 50);
  };

  // Jump to first event of a case
  const handleCasePillClick = (caseId: string) => {
    const idx = timeline.findIndex(e => e.caseId.toLowerCase() === caseId.toLowerCase());
    if (idx >= 0) {
      setActiveEventIndex(idx);
      const el = eventRefs.current[idx];
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      onOpenEvidence(timeline[idx].evidenceId);
      showToast(`Scrolled to first event in ${caseId}`);
    } else {
      showToast(`No recorded events for ${caseId} in demonstration dataset`);
    }
  };

  // Handle chat submission
  const handleSendMessage = (queryToSend?: string) => {
    const text = (queryToSend || chatInput).trim();
    if (!text) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'USER',
      mode: chatMode,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text
    };

    setMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatLoading(true);
    setChatExpanded(true);

    setTimeout(() => {
      const response = assistantService.generateResponse(text, person, filteredTimeline, chatMode);
      setMessages(prev => [...prev, response]);
      setIsChatLoading(false);

      if (response.referencedEvidenceIds && response.referencedEvidenceIds.length > 0) {
        jumpToEvidence(response.referencedEvidenceIds[0]);
      }
    }, 500);
  };

  const handleToggleBookmark = () => {
    const res = storageService.toggleBookmark(person.id);
    setIsBookmarked(res);
    showToast(res ? `Bookmarked ${person.id}` : `Removed bookmark for ${person.id}`);
  };

  const handleExportTimeline = () => {
    exportService.exportTimelineCSV(timeline, person.name);
    showToast(`Exported chronological timeline for ${person.name}`);
  };

  const suggestedQuestions = [
    'How many cases is this person mentioned in?',
    'Which cases record this person as primary suspect?',
    'What financial activity is recorded?',
    'Summarise recorded activity'
  ];

  // Exact type colors from Section 10.3:
  // FIR #c0504a, Communication #4a7fb5, Location #7B8062, Financial #B96D50, Cross-case #8a63b0
  const getModalityColor = (m: Modality | string) => {
    switch (m) {
      case 'FIR': return '#c0504a';
      case 'COMMUNICATION': case 'CDR': return '#4a7fb5';
      case 'LOCATION': return '#7B8062';
      case 'FINANCIAL': return '#B96D50';
      case 'CROSS_CASE': return '#8a63b0';
      default: return '#7B8062';
    }
  };

  return (
    <div className="w-full h-[calc(100vh-68px)] pt-18 overflow-hidden bg-[#FAF6F0] flex flex-col font-sans">
      {/* Top Breadcrumb Navigation Bar */}
      <div className="h-12 border-b border-[#DCCAB0] bg-[#F8F3E9] px-6 flex items-center justify-between shrink-0">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-xs font-serif font-bold text-[#30251F] hover:text-[#B96D50] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>BACK TO INVESTIGATIONS</span>
        </button>

        <div className="flex items-center space-x-3 text-xs font-mono">
          <button
            onClick={handleExportTimeline}
            className="px-3 py-1 rounded-md border border-[#DCCAB0] hover:border-[#A86F45] bg-[#FAF6F0] text-[#30251F] flex items-center space-x-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-[#A86F45]" />
            <span>EXPORT TIMELINE</span>
          </button>

          <button
            onClick={handleToggleBookmark}
            className={`px-3 py-1 rounded-md border text-xs flex items-center space-x-1.5 transition-all ${
              isBookmarked 
                ? 'bg-[#B96D50] text-[#F8F3E9] border-[#B96D50]' 
                : 'border-[#DCCAB0] hover:border-[#A86F45] bg-[#FAF6F0] text-[#433A32]'
            }`}
          >
            <Bookmark className="w-3.5 h-3.5" />
            <span>{isBookmarked ? 'BOOKMARKED' : 'BOOKMARK DOSSIER'}</span>
          </button>
        </div>
      </div>

      {/* Main Split-Screen Container (42% Fixed Left Dossier × 58% Scrolling Right Timeline) */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden p-3 gap-3.5">
        
        {/* ================= 10.2 FIXED LEFT DOSSIER (42% width, Sandstone Card) ================= */}
        <aside className="w-full lg:w-[42%] h-full bg-[#DCCAB0]/35 border border-[#DCCAB0] rounded-2xl p-5 shadow-sm flex flex-col justify-between overflow-y-auto">
          <div>
            {/* Top Row: Terracotta-Pink Pill, Big Serif ID, Guilt Disclaimer */}
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex-1">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-[#B96D50]/15 text-[#B96D50] border border-[#B96D50]/30 inline-block mb-1">
                  PERSON OF INTEREST
                </span>
                <h1 className="font-serif text-4xl lg:text-[44px] font-bold text-[#30251F] tracking-tight leading-none mt-1">
                  {person.id}
                </h1>
                <p className="font-mono text-xs text-[#A86F45] mt-1 font-semibold">
                  {person.name}
                </p>
                <p className="text-[10px] font-sans text-[#433A32]/65 italic mt-0.5">
                  Recorded appearance only, not a finding of guilt
                </p>
              </div>

              {/* Square Portrait (max 190px or 36%) */}
              <div className="w-[36%] max-w-[190px] aspect-square rounded-xl overflow-hidden border border-[#A86F45]/40 shadow-sm shrink-0 bg-[#F5EFEB]">
                <img 
                  src={person.avatarUrl || '/assets/suspect-dossier-reference.jpg'} 
                  alt={person.name} 
                  className="w-full h-full object-cover"
                  style={{ objectPosition: '42% 28%' }}
                />
              </div>
            </div>

            {/* Facts Grid */}
            <div className="pt-3 border-t border-[#A86F45]/25">
              <h4 className="font-mono uppercase text-[10px] tracking-widest text-[#A86F45] font-bold mb-2">
                PERSONAL INFORMATION
              </h4>
              <div className="space-y-1.5 text-xs text-[#433A32]">
                <div className="flex items-center justify-between">
                  <span>Contact numbers:</span>
                  <span className="font-mono font-semibold text-[#30251F]">{person.contactNumbers.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Associated devices:</span>
                  <span className="font-mono font-semibold text-[#30251F]">{person.associatedDevices.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>First appearance:</span>
                  <span className="font-mono font-semibold text-[#30251F]">{person.firstAppearance}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Latest activity:</span>
                  <span className="font-mono font-semibold text-[#B96D50]">{person.latestActivity}</span>
                </div>
              </div>
            </div>

            {/* Two Big Numbers in Serif (40px): 06 Cases mentioned, 02 Primary suspect cases */}
            <div className="mt-5 grid grid-cols-2 gap-4 py-3.5 border-y border-[#A86F45]/30 bg-[#FAF6F0]/60 rounded-xl px-4">
              <div>
                <span className="font-serif text-[40px] font-bold text-[#30251F] block leading-none">
                  {String(person.casesMentioned.length).padStart(2, '0')}
                </span>
                <span className="text-[11px] font-sans text-[#433A32]/85 mt-1 block">
                  Cases mentioned
                </span>
              </div>
              <div className="border-l border-[#A86F45]/30 pl-4">
                <span className="font-serif text-[40px] font-bold text-[#B96D50] block leading-none">
                  {String(person.primarySuspectCases.length).padStart(2, '0')}
                </span>
                <span className="text-[11px] font-sans text-[#433A32]/85 mt-1 block">
                  Primary suspect cases
                </span>
              </div>
            </div>

            {/* Case Involvement Chips (Star marks primary suspect) */}
            <div className="mt-5">
              <h4 className="font-mono uppercase text-[10px] tracking-widest text-[#A86F45] font-bold mb-2">
                CASE INVOLVEMENT
              </h4>
              <div className="flex flex-wrap gap-2">
                {person.casesMentioned.map(cid => {
                  const isPrimary = person.primarySuspectCases.includes(cid);
                  return (
                    <button
                      key={cid}
                      onClick={() => handleCasePillClick(cid)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5 border ${
                        isPrimary
                          ? 'bg-[#B96D50] text-[#F8F3E9] border-[#B96D50] shadow-xs'
                          : 'bg-[#F8F3E9] hover:bg-[#FAF6F0] border-[#DCCAB0] text-[#30251F]'
                      }`}
                      title={isPrimary ? 'Primary Suspect Case — Click to inspect timeline' : 'Click to inspect timeline'}
                    >
                      {isPrimary && <Star className="w-3 h-3 fill-current text-[#F8F3E9]" />}
                      <span>{cid}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Connected Entities Chips */}
            <div className="mt-4">
              <h4 className="font-mono uppercase text-[10px] tracking-widest text-[#A86F45] font-bold mb-1.5">
                CONNECTED ENTITIES
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {person.associatedDevices.map(d => (
                  <span key={d} className="px-2 py-0.5 rounded bg-[#FAF6F0] border border-[#DCCAB0] text-[10px] font-mono text-[#433A32]">
                    {d}
                  </span>
                ))}
                {person.bankAccounts.map(b => (
                  <span key={b} className="px-2 py-0.5 rounded bg-[#FAF6F0] border border-[#DCCAB0] text-[10px] font-mono text-[#A86F45]">
                    {b}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Bottom Action: View Relationship Graph Button */}
          <div className="pt-4 mt-4 border-t border-[#A86F45]/30">
            <button
              onClick={() => setIsGraphDrawerOpen(true)}
              className="w-full py-2.5 px-4 rounded-xl border border-[#A86F45] bg-[#FAF6F0] hover:bg-[#30251F] hover:text-[#F8F3E9] text-[#30251F] font-serif text-xs font-semibold tracking-wider flex items-center justify-center space-x-2 transition-all shadow-xs"
            >
              <Network className="w-4 h-4 text-[#A86F45]" />
              <span>View relationship graph</span>
            </button>
          </div>
        </aside>

        {/* ================= 10.3 & 11 RIGHT PANEL: TIMELINE & CHAT BAR (58% width, Ivory Card) ================= */}
        <main className="w-full lg:w-[58%] h-full flex flex-col justify-between overflow-hidden bg-[#F8F3E9] border border-[#DCCAB0] rounded-2xl shadow-sm">
          
          {/* Timeline Header & Filter Pills */}
          <div className="px-6 py-3.5 border-b border-[#DCCAB0] bg-[#FAF6F0]/80 flex flex-wrap items-center justify-between gap-3 shrink-0">
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="font-serif text-lg font-bold tracking-wide text-[#30251F] uppercase">
                  TEMPORAL ACTIVITY
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-[#7B8062]/20 text-[#7B8062] border border-[#7B8062]/30 uppercase">
                  LIVE DEMO
                </span>
              </div>
              <p className="text-xs text-[#433A32]/70 font-sans">
                Scroll through recorded activity or activate chronological playback
              </p>
            </div>

            {/* Type Filters */}
            <div className="flex items-center space-x-1 text-xs">
              {['ALL', 'FIR', 'COMMUNICATION', 'LOCATION', 'FINANCIAL', 'CROSS_CASE'].map(mod => (
                <button
                  key={mod}
                  onClick={() => setFilterModality(mod)}
                  className={`px-2.5 py-1 rounded-full text-[10px] font-mono transition-all border ${
                    filterModality === mod
                      ? 'bg-[#30251F] text-[#F8F3E9] border-[#30251F]'
                      : 'bg-[#FAF6F0] text-[#433A32] border-[#DCCAB0] hover:border-[#A86F45]'
                  }`}
                >
                  {mod === 'COMMUNICATION' ? 'COMM' : mod === 'LOCATION' ? 'LOC' : mod === 'FINANCIAL' ? 'FIN' : mod === 'CROSS_CASE' ? 'CROSS' : mod}
                </button>
              ))}
            </div>
          </div>

          {/* 10.4 Replay Investigation Controls Ribbon */}
          <div className="px-6 py-2 border-b border-[#DCCAB0]/60 bg-[#DCCAB0]/25 flex items-center justify-between text-xs shrink-0">
            <div className="flex items-center space-x-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#A86F45] font-bold">
                REPLAY INVESTIGATION:
              </span>
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="px-3 py-1 rounded-md bg-[#30251F] hover:bg-[#B96D50] text-[#F8F3E9] text-xs font-serif flex items-center space-x-1.5 transition-colors font-semibold"
              >
                {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isPlaying ? 'PAUSE' : 'REPLAY'}</span>
              </button>

              <button
                onClick={() => {
                  const newIdx = Math.max(0, activeEventIndex - 1);
                  setActiveEventIndex(newIdx);
                  if (filteredTimeline[newIdx]) onOpenEvidence(filteredTimeline[newIdx].evidenceId);
                }}
                className="p-1 rounded bg-[#DCCAB0]/40 hover:bg-[#DCCAB0]/70 text-[#30251F]"
                title="Previous Milestone"
              >
                Prev
              </button>

              <button
                onClick={() => {
                  const newIdx = Math.min(filteredTimeline.length - 1, activeEventIndex + 1);
                  setActiveEventIndex(newIdx);
                  if (filteredTimeline[newIdx]) onOpenEvidence(filteredTimeline[newIdx].evidenceId);
                }}
                className="p-1 rounded bg-[#DCCAB0]/40 hover:bg-[#DCCAB0]/70 text-[#30251F]"
                title="Next Milestone"
              >
                Next
              </button>

              <button
                onClick={() => {
                  setIsPlaying(false);
                  setActiveEventIndex(0);
                  if (timelineContainerRef.current) timelineContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className="p-1 rounded bg-[#DCCAB0]/40 hover:bg-[#DCCAB0]/70 text-[#30251F]"
                title="Reset Replay"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Playback Speed Controls: 1x, 2x, 4x */}
            <div className="flex items-center space-x-1 font-mono text-[11px]">
              <span className="text-[#A86F45] pr-1">Speed:</span>
              {[1, 2, 4].map(s => (
                <button
                  key={s}
                  onClick={() => setPlaybackSpeed(s)}
                  className={`px-2 py-0.5 rounded border ${
                    playbackSpeed === s 
                      ? 'bg-[#B96D50] text-white border-[#B96D50] font-bold' 
                      : 'bg-[#FAF6F0] text-[#30251F] border-[#DCCAB0]'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>

          {/* Independently Scrollable Timeline Events Container */}
          <div 
            ref={timelineContainerRef}
            className="flex-1 overflow-y-auto px-6 py-4 space-y-3 relative"
          >
            {/* Continuous Vertical Copper Spine */}
            <div className="absolute left-[38px] top-6 bottom-6 w-0.5 bg-[#A86F45]/35 pointer-events-none" />

            {filteredTimeline.map((ev, idx) => {
              const isActive = activeEventIndex === idx;
              const typeColor = getModalityColor(ev.modality);

              return (
                <div
                  key={ev.id}
                  ref={el => eventRefs.current[idx] = el}
                  onClick={() => {
                    setActiveEventIndex(idx);
                    onOpenEvidence(ev.evidenceId);
                  }}
                  className={`flex items-start gap-4 p-3.5 rounded-xl border transition-all cursor-pointer relative z-10 ${
                    isActive 
                      ? 'bg-[#FAF6F0] border-[#C69A55] ring-2 ring-[#C69A55]/40 shadow-sm' 
                      : 'bg-[#FAF6F0]/60 hover:bg-[#FAF6F0] border-[#DCCAB0]'
                  }`}
                >
                  {/* Month Pill with 25% tint of the type color */}
                  <div
                    className="w-12 h-10 rounded-lg flex flex-col items-center justify-center shrink-0 border"
                    style={{
                      backgroundColor: `${typeColor}22`,
                      borderColor: `${typeColor}55`,
                      color: typeColor
                    }}
                  >
                    <span className="font-mono text-[11px] font-bold tracking-wider">
                      {ev.monthStr}
                    </span>
                  </div>

                  {/* Coloured Dot on the spine line */}
                  <div
                    className="w-3 h-3 rounded-full border-2 border-[#FAF6F0] shrink-0 mt-2.5 -ml-2"
                    style={{ backgroundColor: typeColor }}
                  />

                  {/* Event Text */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="font-serif font-bold text-sm text-[#30251F]">
                        {ev.dateStr} • {ev.title}
                      </span>
                      <span className="font-mono text-[10px] text-[#A86F45] bg-[#DCCAB0]/30 px-2 py-0.5 rounded">
                        {ev.timeStr}
                      </span>
                    </div>

                    <p className="font-mono text-xs text-[#A86F45] mt-0.5">
                      {ev.caseId} • {ev.timeStr} • {ev.evidenceId}
                    </p>

                    <p className="text-xs text-[#433A32]/85 mt-1 line-clamp-2">
                      {ev.description}
                    </p>
                  </div>
                </div>
              );
            })}

            <div className="text-center font-mono text-[11px] text-[#A86F45] py-2">
              ↓ SCROLL TO EXPLORE MORE EVENTS ↓
            </div>
          </div>

          {/* ================= 11 CONTEXTUAL KRONOS AI CHAT BAR (Bottom of Right Panel) ================= */}
          <div className="border-t border-[#DCCAB0] bg-[#FAF6F0] p-4 shrink-0 space-y-2.5">
            {/* Expandable Conversation Transcript Log (max-height: 200px) */}
            {chatExpanded && (
              <div className="max-h-48 overflow-y-auto space-y-2 pr-1 pb-1 border-b border-[#DCCAB0]/50 font-sans text-xs">
                {messages.map(msg => (
                  <div
                    key={msg.id}
                    className={`p-3 rounded-xl border ${
                      msg.sender === 'USER'
                        ? 'bg-[#F8F3E9] border-[#DCCAB0] ml-8 text-[#30251F]'
                        : 'bg-[#FAF6F0] border-[#C69A55]/40 mr-8 text-[#30251F]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1 text-[10px] font-mono">
                      <span className="font-bold text-[#A86F45]">
                        {msg.sender === 'USER' ? 'INVESTIGATING OFFICER' : `KRONOS AI (${msg.mode})`}
                      </span>
                      <span className="text-[#433A32]/60">{msg.timestamp}</span>
                    </div>
                    <div className="text-xs leading-relaxed whitespace-pre-line">
                      {msg.text}
                    </div>

                    {/* Clickable Evidence Reference Pills in AI Response */}
                    {msg.referencedEvidenceIds && msg.referencedEvidenceIds.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-[#DCCAB0]/40">
                        <span className="text-[10px] font-mono text-[#A86F45]">Cited Evidences:</span>
                        {msg.referencedEvidenceIds.map(eid => (
                          <button
                            key={eid}
                            onClick={() => jumpToEvidence(eid)}
                            className="px-2 py-0.5 rounded bg-[#C69A55]/20 text-[#30251F] hover:bg-[#B96D50] hover:text-white font-mono text-[10px] transition-colors font-semibold"
                          >
                            {eid} ↗
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {isChatLoading && (
                  <div className="p-2 text-xs font-mono text-[#A86F45] animate-pulse">
                    Computing local heuristic response...
                  </div>
                )}
              </div>
            )}

            {/* Chat Input & Controls Row */}
            <div className="flex items-center gap-2">
              <span className="font-serif font-bold text-xs text-[#30251F] shrink-0">
                KRONOS:
              </span>

              {/* Mode Selector Dropdown */}
              <select
                value={chatMode}
                onChange={e => setChatMode(e.target.value as any)}
                className="px-2.5 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#F8F3E9] text-xs font-mono font-semibold text-[#B96D50] focus:outline-none"
              >
                <option value="ASSISTANCE">ASSISTANCE (Factual)</option>
                <option value="DETECTIVE">DETECTIVE (Hypothesis)</option>
              </select>

              {/* Text Input */}
              <input
                type="text"
                placeholder={`Ask about ${person.name} (${person.id})...`}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                className="flex-1 px-3 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#F8F3E9] text-xs text-[#30251F] focus:outline-none focus:border-[#B96D50]"
              />

              <button
                onClick={() => handleSendMessage()}
                className="p-2 bg-[#B96D50] hover:bg-[#A86F45] text-white rounded-lg transition-colors"
                title="Send Question"
              >
                <Send className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => setChatExpanded(!chatExpanded)}
                className="p-2 bg-[#F8F3E9] hover:bg-[#EAE0D2] border border-[#DCCAB0] rounded-lg text-[#30251F] transition-colors"
                title={chatExpanded ? 'Collapse Log' : 'Expand Log'}
              >
                {chatExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
              </button>
            </div>

            {/* Reading From Scope Subline & Suggested Question Chips */}
            <div className="flex flex-wrap items-center justify-between text-[11px] gap-2">
              <span className="font-mono text-[#7B8062]">
                Answering from: {filterModality === 'ALL' ? 'all recorded events' : `filtered timeline only (${filterModality}, ${filteredTimeline.length} events)`}
              </span>

              <div className="flex flex-wrap gap-1.5">
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(q)}
                    className="px-2 py-0.5 rounded-full bg-[#DCCAB0]/35 hover:bg-[#B96D50] hover:text-white border border-[#DCCAB0] text-[10px] text-[#433A32] transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* SVG Relationship Graph Modal / Drawer */}
      {isGraphDrawerOpen && (
        <div className="fixed inset-0 z-50 bg-[#30251F]/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#FAF6F0] w-full max-w-lg rounded-2xl border border-[#DCCAB0] shadow-2xl p-6 relative">
            <div className="flex items-center justify-between pb-3 border-b border-[#DCCAB0]">
              <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-[#B96D50]" />
                <h3 className="font-serif font-bold text-sm text-[#30251F]">
                  Topology Subgraph: {person.name} ({person.id})
                </h3>
              </div>
              <button 
                onClick={() => setIsGraphDrawerOpen(false)}
                className="p-1 rounded hover:bg-[#EAE0D2] text-[#433A32]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* SVG Graph: person center, cases inner ring r=80, entities outer ring r=145 */}
            <div className="py-4 flex items-center justify-center">
              <svg width="340" height="340" viewBox="0 0 340 340" className="overflow-visible">
                {/* Outer Ring Circle */}
                <circle cx="170" cy="170" r="145" fill="none" stroke="#C69A55" strokeOpacity="0.25" strokeDasharray="3 3" />
                {/* Inner Ring Circle */}
                <circle cx="170" cy="170" r="80" fill="none" stroke="#C69A55" strokeOpacity="0.4" strokeDasharray="3 3" />

                {/* Connection Lines from Center */}
                {person.casesMentioned.map((cid, i) => {
                  const angle = (i / person.casesMentioned.length) * Math.PI * 2;
                  const x = 170 + Math.cos(angle) * 80;
                  const y = 170 + Math.sin(angle) * 80;
                  return (
                    <g key={`edge-${cid}`}>
                      <line x1="170" y1="170" x2={x} y2={y} stroke="#C69A55" strokeWidth="1.2" strokeOpacity="0.6" />
                      <circle cx={x} cy={y} r="8" fill="#B96D50" />
                      <text x={x} y={y + 16} textAnchor="middle" fontSize="9" fontFamily="JetBrains Mono" fill="#30251F">{cid}</text>
                    </g>
                  );
                })}

                {/* Outer entities */}
                {person.associatedDevices.concat(person.bankAccounts).slice(0, 6).map((ent, i) => {
                  const angle = (i / 6) * Math.PI * 2 + 0.3;
                  const x = 170 + Math.cos(angle) * 145;
                  const y = 170 + Math.sin(angle) * 145;
                  return (
                    <g key={`ent-${ent}`}>
                      <line x1="170" y1="170" x2={x} y2={y} stroke="#C69A55" strokeWidth="0.8" strokeOpacity="0.35" />
                      <circle cx={x} cy={y} r="6" fill="#7B8062" />
                      <text x={x} y={y + 14} textAnchor="middle" fontSize="8" fontFamily="JetBrains Mono" fill="#7B8062">{ent.slice(0, 8)}</text>
                    </g>
                  );
                })}

                {/* Center Person Dot */}
                <circle cx="170" cy="170" r="16" fill="#30251F" stroke="#C69A55" strokeWidth="2" />
                <text x="170" y="174" textAnchor="middle" fontSize="9" fontFamily="JetBrains Mono" fontWeight="bold" fill="#F8F3E9">{person.id}</text>
              </svg>
            </div>

            <div className="pt-3 border-t border-[#DCCAB0] flex justify-end">
              <button
                onClick={() => {
                  setIsGraphDrawerOpen(false);
                  onViewGraph(person.id);
                }}
                className="px-4 py-2 bg-[#B96D50] hover:bg-[#A86F45] text-white rounded-lg font-serif text-xs font-semibold flex items-center gap-1.5"
              >
                <span>Launch Full 3D Topology Explorer</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profile Toast */}
      {profileToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-[#30251F] text-[#F8F3E9] px-4 py-2 rounded-full font-mono text-xs shadow-xl border border-[#C69A55]/40 animate-fade-in flex items-center gap-2">
          <Check className="w-3.5 h-3.5 text-[#C69A55]" />
          <span>{profileToast}</span>
        </div>
      )}
    </div>
  );
};
