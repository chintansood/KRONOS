import React, { useState, useMemo, useRef, useEffect } from 'react';
import gsap from 'gsap';
import { 
  FolderPlus, Search, Filter, ChevronRight, UserCheck, 
  ExternalLink, ArrowRight, ShieldCheck, Check
} from 'lucide-react';
import { Case, Person } from '../types/investigation';

interface SignatureDashboardProps {
  cases: Case[];
  persons: Person[];
  selectedCaseId: string | null;
  selectedPersonId: string | null;
  onSelectCase: (caseId: string) => void;
  onSelectPerson: (personId: string) => void;
  onOpenCaseWorkspace: (caseId: string) => void;
  onOpenSuspectDossier: (personId: string) => void;
  onAddNewCase: () => void;
}

export const SignatureDashboard: React.FC<SignatureDashboardProps> = ({
  cases,
  persons,
  selectedCaseId,
  selectedPersonId,
  onSelectCase,
  onSelectPerson,
  onOpenCaseWorkspace,
  onOpenSuspectDossier,
  onAddNewCase
}) => {
  // Case filtering & sorting
  const [caseSearch, setCaseSearch] = useState('');
  const [caseStatusFilter, setCaseStatusFilter] = useState<string>('ALL');
  const [caseSortBy, setCaseSortBy] = useState<'LATEST' | 'EVIDENCE' | 'ID'>('LATEST');

  // Person filtering & sorting
  const [personSearch, setPersonSearch] = useState('');
  const [personFilter, setPersonFilter] = useState<'ALL' | 'PRIMARY' | 'CROSS_CASE'>('ALL');
  const [personSortBy, setPersonSortBy] = useState<'CASES' | 'ID'>('CASES');

  // Active toast feedback for metrics
  const [metricToast, setMetricToast] = useState<string | null>(null);

  // SVG EV hub ref for GSAP pulse
  const evHubRef = useRef<SVGCircleElement>(null);

  // Trigger pulse on selection change
  useEffect(() => {
    if (evHubRef.current) {
      gsap.fromTo(
        evHubRef.current,
        { r: 9 },
        { r: 16, duration: 0.3, yoyo: true, repeat: 1, ease: 'power2.out' }
      );
    }
  }, [selectedCaseId, selectedPersonId]);

  // Active entities
  const activeCase = useMemo(() => cases.find(c => c.id === selectedCaseId), [cases, selectedCaseId]);
  const activePerson = useMemo(() => persons.find(p => p.id === selectedPersonId), [persons, selectedPersonId]);

  // Connected entity lookups
  const linkedPersonIds = useMemo(() => {
    if (!activeCase) return new Set<string>();
    return new Set(activeCase.personIds);
  }, [activeCase]);

  const linkedCaseIds = useMemo(() => {
    if (!activePerson) return new Set<string>();
    return new Set(activePerson.caseIds);
  }, [activePerson]);

  // Toggle selection (Clicking same row unselects)
  const handleCaseClick = (cid: string) => {
    if (selectedCaseId === cid) {
      onSelectCase('');
    } else {
      onSelectCase(cid);
    }
  };

  const handlePersonClick = (pid: string) => {
    if (selectedPersonId === pid) {
      onSelectPerson('');
    } else {
      onSelectPerson(pid);
    }
  };

  // Metrics filtering click
  const triggerMetricFilter = (type: string, label: string) => {
    setMetricToast(`Filtered view applied: ${label}`);
    setTimeout(() => setMetricToast(null), 1800);

    if (type === 'ACTIVE_CASES') setCaseStatusFilter('ACTIVE');
    if (type === 'ALL_CASES') setCaseStatusFilter('ALL');
    if (type === 'PRIMARY') setPersonFilter('PRIMARY');
    if (type === 'CROSS_CASE') setPersonFilter('CROSS_CASE');
  };

  // Filter & sort cases
  const filteredCases = useMemo(() => {
    return cases
      .filter(c => {
        const matchesSearch = 
          c.id.toLowerCase().includes(caseSearch.toLowerCase()) ||
          c.title.toLowerCase().includes(caseSearch.toLowerCase()) ||
          c.offenceCategory.toLowerCase().includes(caseSearch.toLowerCase());
        const matchesStatus = caseStatusFilter === 'ALL' || c.status === caseStatusFilter;
        return matchesSearch && matchesStatus;
      })
      .sort((a, b) => {
        if (caseSortBy === 'LATEST') return (b.lastActivity || '').localeCompare(a.lastActivity || '');
        if (caseSortBy === 'EVIDENCE') return b.evidenceCount - a.evidenceCount;
        return a.id.localeCompare(b.id);
      });
  }, [cases, caseSearch, caseStatusFilter, caseSortBy]);

  // Filter & sort persons
  const filteredPersons = useMemo(() => {
    return persons
      .filter(p => {
        const matchesSearch = 
          p.id.toLowerCase().includes(personSearch.toLowerCase()) ||
          p.name.toLowerCase().includes(personSearch.toLowerCase()) ||
          (p.alias && p.alias.toLowerCase().includes(personSearch.toLowerCase()));
        
        let matchesFilter = true;
        if (personFilter === 'PRIMARY') {
          matchesFilter = p.primarySuspectCases.length >= 1;
        } else if (personFilter === 'CROSS_CASE') {
          matchesFilter = p.casesMentioned.length >= 3;
        }
        return matchesSearch && matchesFilter;
      })
      .sort((a, b) => {
        if (personSortBy === 'CASES') return b.casesMentioned.length - a.casesMentioned.length;
        return a.id.localeCompare(b.id);
      });
  }, [persons, personSearch, personFilter, personSortBy]);

  // Metrics summary
  const totalCasesCount = cases.length;
  const activeCasesCount = cases.filter(c => c.status === 'ACTIVE').length;
  const totalPersonsCount = persons.length;
  const crossCaseCount = persons.filter(p => p.casesMentioned.length >= 2).length;
  const totalEvidenceCount = cases.reduce((acc, c) => acc + (c.evidenceCount || 0), 0);

  return (
    <div className="w-full min-h-[calc(100vh-68px)] pt-20 pb-8 px-6 font-sans text-[#30251F] relative">
      {/* 9.5 Top Metric Chips Ribbon */}
      <div className="max-w-[1520px] mx-auto mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            onClick={() => triggerMetricFilter('ALL_CASES', 'Total Cases')}
            className="px-3.5 py-1.5 rounded-lg bg-[#F8F3E9] border border-[#DCCAB0] hover:border-[#B96D50] transition-colors flex items-center gap-2 shadow-xs"
          >
            <span className="font-mono text-[#A86F45]">Total Cases:</span>
            <span className="font-serif font-bold text-[#30251F]">{totalCasesCount}</span>
          </button>

          <button
            onClick={() => triggerMetricFilter('ACTIVE_CASES', 'Active Dockets')}
            className="px-3.5 py-1.5 rounded-lg bg-[#F8F3E9] border border-[#DCCAB0] hover:border-[#B96D50] transition-colors flex items-center gap-2 shadow-xs"
          >
            <span className="w-2 h-2 rounded-full bg-[#B96D50] animate-pulse"></span>
            <span className="font-mono text-[#A86F45]">Active Dockets:</span>
            <span className="font-serif font-bold text-[#30251F]">{activeCasesCount}</span>
          </button>

          <button
            onClick={() => triggerMetricFilter('ALL_CASES', 'People Referenced')}
            className="px-3.5 py-1.5 rounded-lg bg-[#F8F3E9] border border-[#DCCAB0] hover:border-[#B96D50] transition-colors flex items-center gap-2 shadow-xs"
          >
            <span className="font-mono text-[#A86F45]">People Referenced:</span>
            <span className="font-serif font-bold text-[#30251F]">{totalPersonsCount}</span>
          </button>

          <button
            onClick={() => triggerMetricFilter('CROSS_CASE', 'Cross-Case Appearances')}
            className="px-3.5 py-1.5 rounded-lg bg-[#F8F3E9] border border-[#DCCAB0] hover:border-[#B96D50] transition-colors flex items-center gap-2 shadow-xs"
          >
            <span className="font-mono text-[#A86F45]">Cross-Case Links:</span>
            <span className="font-serif font-bold text-[#B96D50]">{crossCaseCount}</span>
          </button>

          <button
            onClick={() => triggerMetricFilter('ALL_CASES', 'Evidence Records')}
            className="px-3.5 py-1.5 rounded-lg bg-[#F8F3E9] border border-[#DCCAB0] hover:border-[#B96D50] transition-colors flex items-center gap-2 shadow-xs"
          >
            <span className="font-mono text-[#A86F45]">Evidence Records:</span>
            <span className="font-serif font-bold text-[#30251F]">{totalEvidenceCount}</span>
          </button>
        </div>

        {/* Register New Case Action */}
        <button
          onClick={onAddNewCase}
          className="px-4 py-2 bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] rounded-lg font-serif text-xs font-semibold tracking-wider flex items-center gap-2 shadow-sm transition-all"
        >
          <FolderPlus className="w-4 h-4" />
          <span>REGISTER NEW CASE</span>
        </button>
      </div>

      {/* 9.1 Three-Column Grid: 1fr 70px 1fr */}
      <div className="max-w-[1520px] mx-auto grid grid-cols-1 lg:grid-cols-[1fr_70px_1fr] gap-0 items-stretch h-[calc(100vh-170px)] min-h-[640px]">
        {/* ================= LEFT PANE: ACTIVE CASES (Ivory Card, 14px radius) ================= */}
        <section className="bg-[#F8F3E9] border border-[#DCCAB0] rounded-[14px] p-5 shadow-sm flex flex-col h-full overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-[#DCCAB0]">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#B96D50]"></span>
                <h2 className="font-serif text-lg font-bold tracking-wide text-[#30251F] uppercase">
                  Active Cases
                </h2>
              </div>
              <p className="text-xs text-[#433A32]/70 font-sans mt-0.5">
                Multi-jurisdictional FIR dockets and syndicate operations
              </p>
            </div>
            <span className="font-mono text-[11px] text-[#A86F45] bg-[#FAF6F0] px-2.5 py-1 rounded border border-[#DCCAB0]">
              {filteredCases.length} DOCKETS
            </span>
          </div>

          {/* Controls: Search, Filter, Sort */}
          <div className="py-3 flex flex-wrap gap-2 items-center justify-between border-b border-[#DCCAB0] text-xs">
            <div className="relative flex-1 min-w-[160px]">
              <Search className="w-3.5 h-3.5 text-[#A86F45] absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={caseSearch}
                onChange={e => setCaseSearch(e.target.value)}
                placeholder="Search case ID (CASE-014), title, category..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] focus:outline-none focus:border-[#B96D50] text-xs text-[#30251F] font-sans"
              />
            </div>

            <div className="flex items-center space-x-2">
              <select
                value={caseStatusFilter}
                onChange={e => setCaseStatusFilter(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] text-xs text-[#433A32] focus:outline-none"
              >
                <option value="ALL">All Status</option>
                <option value="ACTIVE">Active</option>
                <option value="UNDER_REVIEW">Under Review</option>
                <option value="CHARGE_SHEETED">Charge Sheeted</option>
              </select>

              <select
                value={caseSortBy}
                onChange={e => setCaseSortBy(e.target.value as any)}
                className="px-2.5 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] text-xs text-[#433A32] focus:outline-none"
              >
                <option value="LATEST">Sort: Latest</option>
                <option value="EVIDENCE">Sort: Evidence count</option>
                <option value="ID">Sort: Case ID</option>
              </select>
            </div>
          </div>

          {/* Scrollable Cases List */}
          <div className="flex-1 overflow-y-auto space-y-2.5 pt-3 pr-1">
            {filteredCases.map(c => {
              const isSelected = selectedCaseId === c.id;
              const isLinked = linkedCaseIds.has(c.id);
              const isDimmed = Boolean(selectedPersonId && !isLinked);

              return (
                <div
                  key={c.id}
                  onClick={() => handleCaseClick(c.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer relative ${
                    isSelected
                      ? 'bg-[#FAF6F0] border-[#B96D50] shadow-md ring-1 ring-[#B96D50]'
                      : isLinked
                      ? 'bg-[#FBF8F3] border-[#C69A55] ring-1 ring-[#C69A55]/40 shadow-xs'
                      : 'bg-[#FAF6F0]/60 hover:bg-[#FAF6F0] border-[#DCCAB0]/80'
                  } ${isDimmed ? 'opacity-35 hover:opacity-100' : 'opacity-100'}`}
                >
                  {/* Left accent bar: terracotta if sel, gold if rel */}
                  <div className={`absolute top-0 left-0 bottom-0 w-1.5 ${
                    isSelected ? 'bg-[#B96D50]' : isLinked ? 'bg-[#C69A55]' : 'bg-transparent'
                  }`} />

                  <div className="pl-2">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-[#A86F45]">{c.id}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-[#DCCAB0]/40 text-[#433A32] border border-[#DCCAB0]">
                          {c.offenceCategory}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#30251F] text-[#F8F3E9] uppercase">
                        {c.status.replace(/_/g, ' ')}
                      </span>
                    </div>

                    <h3 className="font-serif font-bold text-sm text-[#30251F] leading-snug">
                      {c.title}
                    </h3>

                    <p className="text-xs text-[#433A32]/80 line-clamp-2 mt-1">
                      {c.description}
                    </p>

                    <div className="flex items-center justify-between pt-3 mt-2 border-t border-[#DCCAB0]/50 text-[11px] font-mono text-[#A86F45]">
                      <span>{c.peopleCount} People involved</span>
                      <span>•</span>
                      <span>{c.evidenceCount} Evidences</span>
                      <span>•</span>
                      <span>{c.priority} Priority</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Bottom Action Button if a case is selected */}
          {selectedCaseId && activeCase && (
            <div className="pt-3 border-t border-[#DCCAB0] mt-2">
              <button
                onClick={() => onOpenCaseWorkspace(selectedCaseId)}
                className="w-full py-2.5 px-4 bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] rounded-lg font-serif text-xs font-semibold tracking-wider flex items-center justify-center gap-2 transition-colors shadow-sm"
              >
                <span>OPEN CASE WORKSPACE ({activeCase.id})</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </section>

        {/* ================= MIDDLE: 70px EV HUB ================= */}
        <div className="hidden lg:flex flex-col items-center justify-center relative pointer-events-none select-none">
          <svg className="w-full h-full" viewBox="0 0 70 600" preserveAspectRatio="none">
            {/* Gold dotted line connecting the two worlds */}
            <line
              x1="35"
              y1="40"
              x2="35"
              y2="560"
              stroke="#C69A55"
              strokeWidth="1.5"
              strokeDasharray="3 6"
              strokeOpacity="0.7"
            />
            {/* Horizontal branch ticks */}
            <line x1="15" y1="300" x2="55" y2="300" stroke="#C69A55" strokeWidth="1" strokeOpacity="0.5" />
          </svg>

          {/* Central Pulsing EV Hub */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center pointer-events-auto">
            <svg width="48" height="48" viewBox="0 0 48 48" className="overflow-visible">
              <circle
                ref={evHubRef}
                cx="24"
                cy="24"
                r="11"
                fill="#F2E9DA"
                stroke="#C69A55"
                strokeWidth="2.5"
                className="drop-shadow-sm transition-all"
              />
              <text
                x="24"
                y="28"
                textAnchor="middle"
                fontSize="10"
                fontFamily="JetBrains Mono"
                fontWeight="bold"
                fill="#30251F"
              >
                EV
              </text>
            </svg>
            <span className="font-mono text-[9px] uppercase tracking-widest text-[#A86F45] mt-1 font-semibold">
              EVIDENCE
            </span>
          </div>
        </div>

        {/* ================= RIGHT PANE: PERSONS OF INTEREST (Sandstone Card, 14px radius) ================= */}
        <section className="bg-[#DCCAB0]/45 border border-[#DCCAB0] rounded-[14px] p-5 shadow-sm flex flex-col h-full overflow-hidden mt-6 lg:mt-0">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-[#A86F45]/30">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#A86F45]"></span>
                <h2 className="font-serif text-lg font-bold tracking-wide text-[#30251F] uppercase">
                  Persons of Investigative Interest
                </h2>
              </div>
              <p className="text-xs text-[#433A32]/70 font-sans mt-0.5">
                Recorded appearance only, not a finding of guilt
              </p>
            </div>
            <span className="font-mono text-[11px] text-[#A86F45] bg-[#FAF6F0] px-2.5 py-1 rounded border border-[#DCCAB0]">
              {filteredPersons.length} IDENTIFIED
            </span>
          </div>

          {/* Controls: Search, Filter, Sort */}
          <div className="py-3 flex flex-wrap gap-2 items-center justify-between border-b border-[#A86F45]/30 text-xs">
            <div className="relative flex-1 min-w-[160px]">
              <Search className="w-3.5 h-3.5 text-[#A86F45] absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={personSearch}
                onChange={e => setPersonSearch(e.target.value)}
                placeholder="Search name (Rohan Mehta), ID, alias..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] focus:outline-none focus:border-[#B96D50] text-xs text-[#30251F] font-sans"
              />
            </div>

            <div className="flex items-center space-x-2">
              <select
                value={personFilter}
                onChange={e => setPersonFilter(e.target.value as any)}
                className="px-2.5 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] text-xs text-[#433A32] focus:outline-none"
              >
                <option value="ALL">All Persons</option>
                <option value="PRIMARY">Primary suspect in 1+</option>
                <option value="CROSS_CASE">Cross-case (3+)</option>
              </select>

              <select
                value={personSortBy}
                onChange={e => setPersonSortBy(e.target.value as any)}
                className="px-2.5 py-1.5 rounded-lg border border-[#DCCAB0] bg-[#FAF6F0] text-xs text-[#433A32] focus:outline-none"
              >
                <option value="CASES">Sort: Number of cases</option>
                <option value="ID">Sort: Person ID</option>
              </select>
            </div>
          </div>

          {/* Scrollable Persons List */}
          <div className="flex-1 overflow-y-auto space-y-2.5 pt-3 pr-1">
            {filteredPersons.map(p => {
              const isSelected = selectedPersonId === p.id;
              const isLinked = linkedPersonIds.has(p.id);
              const isDimmed = Boolean(selectedCaseId && !isLinked);

              return (
                <div
                  key={p.id}
                  onClick={() => handlePersonClick(p.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer relative ${
                    isSelected
                      ? 'bg-[#FAF6F0] border-[#B96D50] shadow-md ring-1 ring-[#B96D50]'
                      : isLinked
                      ? 'bg-[#FBF8F3] border-[#C69A55] ring-1 ring-[#C69A55]/40 shadow-xs'
                      : 'bg-[#FAF6F0]/70 hover:bg-[#FAF6F0] border-[#DCCAB0]/80'
                  } ${isDimmed ? 'opacity-35 hover:opacity-100' : 'opacity-100'}`}
                >
                  {/* Left accent bar: terracotta if sel, gold if rel */}
                  <div className={`absolute top-0 left-0 bottom-0 w-1.5 ${
                    isSelected ? 'bg-[#B96D50]' : isLinked ? 'bg-[#C69A55]' : 'bg-transparent'
                  }`} />

                  <div className="flex items-center gap-3 pl-2">
                    {/* Avatar */}
                    <div className="w-12 h-12 rounded-lg border border-[#A86F45]/40 overflow-hidden bg-[#FAF6F0] flex items-center justify-center shrink-0">
                      {p.avatarUrl ? (
                        <img src={p.avatarUrl} alt={p.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="font-serif font-bold text-sm text-[#30251F]">
                          {p.name.slice(0, 2).toUpperCase()}
                        </span>
                      )}
                    </div>

                    {/* Person Details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-[#B96D50]">{p.id}</span>
                          <span className="font-serif font-bold text-sm text-[#30251F] truncate">{p.name}</span>
                        </div>
                        {p.primarySuspectCases.length > 0 && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#B96D50]/15 text-[#B96D50] border border-[#B96D50]/30 font-semibold">
                            Primary Suspect ({p.primarySuspectCases.length})
                          </span>
                        )}
                      </div>

                      <div className="text-xs text-[#433A32]/85 flex items-center gap-2 mb-1">
                        <span>Mentioned in <strong>{p.casesMentioned.length} cases</strong></span>
                        <span>•</span>
                        <span>Primary in <strong>{p.primarySuspectCases.length} cases</strong></span>
                      </div>

                      <div className="flex items-center justify-between text-[11px] font-mono text-[#A86F45]">
                        <span>First: {p.firstAppearance}</span>
                        <span>Latest: {p.latestActivity}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Bottom Action Button if a person is selected */}
          {selectedPersonId && activePerson && (
            <div className="pt-3 border-t border-[#A86F45]/30 mt-2">
              <button
                onClick={() => onOpenSuspectDossier(selectedPersonId)}
                className="w-full py-2.5 px-4 bg-[#30251F] hover:bg-[#433A32] text-[#F8F3E9] rounded-lg font-serif text-xs font-semibold tracking-wider flex items-center justify-center gap-2 transition-colors shadow-sm"
              >
                <span>OPEN PROFILE ({activePerson.name})</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Floating Metric Toast Feedback */}
      {metricToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-[#30251F] text-[#F8F3E9] px-4 py-2 rounded-full font-mono text-xs shadow-xl border border-[#C69A55]/40 animate-fade-in flex items-center gap-2">
          <Check className="w-3.5 h-3.5 text-[#C69A55]" />
          <span>{metricToast}</span>
        </div>
      )}
    </div>
  );
};
