import React, { useState } from 'react';
import { 
  ArrowLeft, Download, FileText, Users, DollarSign, Calendar, Clock, 
  ShieldAlert, Send, Sparkles, Brain, CheckCircle, ExternalLink, Plus, Edit3 
} from 'lucide-react';
import { Case, EvidenceRecord, Person, ChatMessage } from '../types/investigation';
import { exportService } from '../services/exportService';

interface CaseWorkspaceProps {
  currentCase: Case;
  allPersons: Person[];
  evidenceList: EvidenceRecord[];
  onBack: () => void;
  onOpenPerson: (personId: string) => void;
  onOpenEvidence: (evidenceId: string) => void;
  onEditCase: (c: Case) => void;
}

export const CaseWorkspace: React.FC<CaseWorkspaceProps> = ({
  currentCase,
  allPersons,
  evidenceList,
  onBack,
  onOpenPerson,
  onOpenEvidence,
  onEditCase
}) => {
  const [activeTab, setActiveTab] = useState<'OVERVIEW' | 'EVIDENCE' | 'ASSISTANCE' | 'DETECTIVE'>('OVERVIEW');
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'c-init',
      sender: 'KRONOS_AI',
      mode: 'ASSISTANCE',
      timestamp: '10:00 AM',
      text: `Investigation workspace active for **${currentCase.id} — ${currentCase.title}**. Ask me about the FIR particulars, accused entities, financial volumes, or switch to Detective mode for pattern leads.`,
      referencedCaseIds: [currentCase.id]
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);

  const casePersons = allPersons.filter(p => currentCase.personIds.includes(p.id));
  const caseEvidence = evidenceList.filter(e => e.caseId === currentCase.id);

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;
    const q = chatInput.trim().toLowerCase();
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: 'USER',
      mode: activeTab === 'DETECTIVE' ? 'DETECTIVE' : 'ASSISTANCE',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: chatInput.trim()
    };
    setMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsLoading(true);

    setTimeout(() => {
      let aiText = '';
      let citations: string[] = [];

      if (activeTab === 'ASSISTANCE') {
        if (q.includes('fir') || q.includes('report') || q.includes('offence')) {
          aiText = `According to **${currentCase.firNumber}** registered at **${currentCase.policeStation} (${currentCase.district})**, the offence is categorized as **${currentCase.offenceCategory}**. Incident occurred on **${currentCase.incidentDate}** and was registered on **${currentCase.registrationDate}** (Reporting Delay: **${currentCase.reportingDelayHours} hours**).`;
        } else if (q.includes('suspect') || q.includes('accused') || q.includes('people')) {
          aiText = `Case **${currentCase.id}** lists **${currentCase.peopleCount} individuals**. Primary accused on record: **${currentCase.primarySuspectIds.join(', ') || 'Under evaluation'}**. Linked network persons: **${currentCase.personIds.join(', ')}**.`;
        } else if (q.includes('money') || q.includes('financial') || q.includes('amount')) {
          aiText = `Total recorded financial volume in this docket: **₹${currentCase.totalFinancialVolume.toLocaleString('en-IN')}**. Evidence includes corporate ledger sweeps and RTGS bank transfers.`;
          citations = ['EVID-014-001'];
        } else {
          aiText = `**Factual Summary for ${currentCase.id}**:\n${currentCase.description}\nLead Investigator: ${currentCase.leadInvestigator}. Active Evidence count: ${currentCase.evidenceCount} verified records.`;
        }
      } else {
        // Detective mode
        aiText = `[DEMO ANALYSIS: PATTERN INSIGHT]\nCross-case correlation indicates that suspects **${currentCase.primarySuspectIds[0] || 'P-0427'}** and **P-0299** exhibit synchronized communication bursts prior to major transaction releases.\n\n**Investigative Hypothesis**: Layered front entity used to absorb customs audit scrutiny. Recommendation: Issue notice to sub-registrar for property registries linked to CASE-021.`;
        citations = ['EVID-014-002', 'EVID-017-003'];
      }

      setMessages(prev => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: 'KRONOS_AI',
          mode: activeTab === 'DETECTIVE' ? 'DETECTIVE' : 'ASSISTANCE',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          text: aiText,
          referencedEvidenceIds: citations,
          referencedCaseIds: [currentCase.id]
        }
      ]);
      setIsLoading(false);
    }, 500);
  };

  const handleExportSummary = () => {
    exportService.exportCaseSummary(currentCase, caseEvidence);
  };

  return (
    <div className="w-full min-h-[calc(100vh-73px)] bg-parchment-texture p-6 lg:p-8 flex flex-col space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-copper/30">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBack}
            className="p-2 rounded-full border border-delicate hover:border-copper bg-parchment-light text-espresso transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-mono text-xs font-bold text-terracotta">{currentCase.id}</span>
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-sandstone/30 border border-delicate">
                {currentCase.firNumber}
              </span>
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-espresso text-parchment uppercase">
                {currentCase.status.replace('_', ' ')}
              </span>
            </div>
            <h1 className="font-serif text-2xl lg:text-3xl font-bold text-espresso mt-1">
              {currentCase.title}
            </h1>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => onEditCase(currentCase)}
            className="px-3.5 py-2 rounded-lg border border-delicate bg-parchment-light hover:border-copper text-xs font-serif tracking-wider text-espresso flex items-center space-x-1.5 transition-colors"
          >
            <Edit3 className="w-3.5 h-3.5 text-copper" />
            <span>EDIT DOCKET</span>
          </button>

          <button
            onClick={handleExportSummary}
            className="px-4 py-2 rounded-lg bg-terracotta hover:bg-terracotta-dark text-white text-xs font-serif tracking-wider flex items-center space-x-2 shadow-sm transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>EXPORT SUMMARY</span>
          </button>
        </div>
      </div>

      {/* Case Key Metadata Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-delicate bg-parchment-light/80 shadow-xs">
          <span className="text-[10px] font-mono uppercase text-copper block mb-1">Offence Classification</span>
          <span className="font-serif font-bold text-sm text-espresso">{currentCase.offenceCategory}</span>
        </div>
        <div className="p-4 rounded-xl border border-delicate bg-parchment-light/80 shadow-xs">
          <span className="text-[10px] font-mono uppercase text-copper block mb-1">Financial Volume</span>
          <span className="font-serif font-bold text-sm text-terracotta">₹{currentCase.totalFinancialVolume.toLocaleString('en-IN')}</span>
        </div>
        <div className="p-4 rounded-xl border border-delicate bg-parchment-light/80 shadow-xs">
          <span className="text-[10px] font-mono uppercase text-copper block mb-1">Station & District</span>
          <span className="font-serif font-bold text-sm text-espresso">{currentCase.policeStation}, {currentCase.district}</span>
        </div>
        <div className="p-4 rounded-xl border border-delicate bg-parchment-light/80 shadow-xs">
          <span className="text-[10px] font-mono uppercase text-copper block mb-1">Lead Officer</span>
          <span className="font-serif font-bold text-sm text-espresso">{currentCase.leadInvestigator}</span>
        </div>
      </div>

      {/* Workspace Tabs */}
      <div className="flex border-b border-delicate space-x-2 text-xs font-serif tracking-wider">
        {[
          { key: 'OVERVIEW', label: 'OVERVIEW & ENTITIES' },
          { key: 'EVIDENCE', label: `EVIDENCE LOG (${caseEvidence.length})` },
          { key: 'ASSISTANCE', label: 'KRONOS ASSISTANCE' },
          { key: 'DETECTIVE', label: 'KRONOS DETECTIVE (ANALYTICS)' },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key as any)}
            className={`px-4 py-2 border-b-2 font-bold transition-all ${
              activeTab === t.key
                ? 'border-terracotta text-terracotta bg-parchment-light/50 rounded-t-lg'
                : 'border-transparent text-charcoal/70 hover:text-espresso'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Overview & Entities */}
      {activeTab === 'OVERVIEW' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 bg-parchment-light/80 border border-delicate rounded-2xl p-6 shadow-sm">
            <h3 className="font-serif font-bold text-base text-espresso mb-2">Narrative & Chronological Scope</h3>
            <p className="text-sm font-sans text-charcoal/90 leading-relaxed whitespace-pre-line">
              {currentCase.description}
            </p>

            <div className="mt-6 pt-4 border-t border-delicate grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
              <div>
                <span className="text-copper block text-[10px] uppercase">Incident Timestamp</span>
                <span className="font-semibold text-espresso">{currentCase.incidentDate}</span>
              </div>
              <div>
                <span className="text-copper block text-[10px] uppercase">Registration Timestamp</span>
                <span className="font-semibold text-espresso">{currentCase.registrationDate}</span>
              </div>
              <div>
                <span className="text-copper block text-[10px] uppercase">Reporting Delay</span>
                <span className="font-semibold text-terracotta">{currentCase.reportingDelayHours} Hours</span>
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 bg-parchment-light/80 border border-delicate rounded-2xl p-6 shadow-sm">
            <h3 className="font-serif font-bold text-base text-espresso mb-3">Associated People ({casePersons.length})</h3>
            <div className="space-y-3">
              {casePersons.map(p => {
                const isPrimary = currentCase.primarySuspectIds.includes(p.id);
                return (
                  <div
                    key={p.id}
                    onClick={() => onOpenPerson(p.id)}
                    className="p-3 rounded-xl border border-delicate bg-parchment/60 hover:bg-parchment hover:border-copper transition-all cursor-pointer flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-xs font-bold text-terracotta">{p.id}</span>
                        {isPrimary && (
                          <span className="text-[9px] uppercase px-1.5 py-0.2 bg-terracotta text-white rounded font-mono">
                            Primary
                          </span>
                        )}
                      </div>
                      <span className="font-serif font-bold text-sm text-espresso block">{p.name}</span>
                      <span className="text-[11px] text-charcoal/70 font-sans">{p.contactNumbers[0]}</span>
                    </div>
                    <ExternalLink className="w-4 h-4 text-copper" />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Evidence Catalog */}
      {activeTab === 'EVIDENCE' && (
        <div className="space-y-3">
          {caseEvidence.map(ev => (
            <div
              key={ev.evidenceId}
              onClick={() => onOpenEvidence(ev.evidenceId)}
              className="p-4 rounded-xl border border-delicate bg-parchment-light/80 hover:bg-parchment hover:border-copper transition-all cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs"
            >
              <div>
                <div className="flex items-center space-x-2 mb-1">
                  <span className="font-mono text-xs font-bold text-copper">{ev.evidenceId}</span>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-sandstone/30 border border-delicate">
                    {ev.modality}
                  </span>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-espresso text-parchment">
                    Reliability: {ev.sourceReliability}
                  </span>
                </div>
                <p className="text-xs font-sans text-espresso font-medium leading-relaxed">
                  {ev.description}
                </p>
                <div className="flex items-center space-x-3 text-[11px] font-mono text-charcoal/70 mt-1">
                  <span>{ev.locationName}</span>
                  <span>•</span>
                  <span>{ev.timestamp}</span>
                  <span>•</span>
                  <span>People: {ev.relatedPersonIds.join(', ')}</span>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenEvidence(ev.evidenceId);
                }}
                className="px-3 py-1.5 rounded-lg border border-delicate hover:bg-terracotta hover:text-white text-xs font-serif transition-colors"
              >
                Inspect
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Tab 3 & 4: Assistance and Detective Chat Interfaces */}
      {(activeTab === 'ASSISTANCE' || activeTab === 'DETECTIVE') && (
        <div className="bg-parchment-light/90 border border-copper/30 rounded-2xl p-6 shadow-warm flex flex-col h-[520px]">
          <div className="pb-3 border-b border-delicate flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className={`w-2.5 h-2.5 rounded-full ${activeTab === 'DETECTIVE' ? 'bg-terracotta' : 'bg-copper'}`}></span>
              <span className="font-serif font-bold text-sm text-espresso uppercase">
                {activeTab === 'DETECTIVE' ? 'KRONOS DETECTIVE — ANALYTICAL PATTERNS' : 'KRONOS ASSISTANCE — FACTUAL GROUNDING'}
              </span>
            </div>
            <span className="text-[10px] font-mono uppercase text-copper">
              {activeTab === 'DETECTIVE' ? 'DEMO ANALYSIS ONLY' : 'STRICTLY EVIDENCE GROUNDED'}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto py-4 space-y-3">
            {messages.map(m => (
              <div
                key={m.id}
                className={`p-3.5 rounded-xl text-xs font-sans leading-relaxed ${
                  m.sender === 'USER'
                    ? 'bg-sandstone/40 ml-12 text-espresso font-medium'
                    : 'bg-parchment border border-copper/30 mr-8 text-espresso shadow-xs'
                }`}
              >
                <div className="flex items-center space-x-2 font-mono text-[10px] text-copper mb-1">
                  <span className="font-bold">{m.sender === 'USER' ? 'INVESTIGATOR' : `KRONOS ${m.mode}`}</span>
                  <span>•</span>
                  <span>{m.timestamp}</span>
                </div>
                <div className="whitespace-pre-line">{m.text}</div>

                {m.referencedEvidenceIds && m.referencedEvidenceIds.length > 0 && (
                  <div className="mt-2 pt-1 border-t border-delicate flex flex-wrap gap-1 items-center">
                    <span className="text-[10px] font-mono text-copper uppercase">Citations:</span>
                    {m.referencedEvidenceIds.map(evId => (
                      <button
                        key={evId}
                        onClick={() => onOpenEvidence(evId)}
                        className="px-2 py-0.5 rounded bg-sandstone/30 hover:bg-terracotta hover:text-white border border-delicate text-[10px] font-mono"
                      >
                        {evId}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="text-xs font-mono text-copper p-2 flex items-center space-x-2 animate-pulse">
                <Brain className="w-4 h-4 animate-spin" />
                <span>Scanning case docket particulars...</span>
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-delicate flex items-center space-x-2">
            <input
              type="text"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
              placeholder={activeTab === 'DETECTIVE' ? "Ask about syndicate patterns, leads, or hypotheses..." : "Ask what the FIR states, who is mentioned, or financial totals..."}
              className="flex-1 bg-parchment/60 border border-delicate rounded-lg px-3.5 py-2 text-xs font-sans text-espresso focus:outline-none focus:border-copper"
            />
            <button
              onClick={handleSendMessage}
              className="px-4 py-2 bg-terracotta hover:bg-terracotta-dark text-white rounded-lg text-xs font-serif tracking-wider flex items-center space-x-1.5"
            >
              <span>QUERY</span>
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

