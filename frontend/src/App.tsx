import React, { useState, useEffect } from 'react';
import { Navigation } from './components/Navigation';
import { HeroExperience } from './components/HeroExperience';
import { SignatureDashboard } from './components/SignatureDashboard';
import { SuspectProfile } from './components/SuspectProfile';
import { CaseWorkspace } from './components/CaseWorkspace';
import { ThreeRelationshipGraph } from './components/ThreeRelationshipGraph';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { CaseModal } from './components/CaseModal';
import { NotificationDrawer } from './components/NotificationDrawer';
import { SettingsModal } from './components/SettingsModal';
import { ArchivalBackground } from './components/ArchivalBackground';

import { Case, Person, EvidenceRecord, TimelineEvent } from './types/investigation';
import { storageService } from './services/storageService';
import { CheckCircle2 } from 'lucide-react';

export const App: React.FC = () => {
  // Navigation & View state
  const [currentView, setCurrentView] = useState<'HERO' | 'DASHBOARD' | 'SUSPECT' | 'CASE' | 'GRAPH'>('HERO');
  const [selectedCaseId, setSelectedCaseId] = useState<string>('CASE-014');
  const [selectedPersonId, setSelectedPersonId] = useState<string>('P-0427');

  // Core Data loaded from storage
  const [cases, setCases] = useState<Case[]>(() => storageService.getCases());
  const [persons, setPersons] = useState<Person[]>(() => storageService.getPersons());
  const [allEvidence, setAllEvidence] = useState<EvidenceRecord[]>(() => storageService.getAllEvidence());
  const [timeline, setTimeline] = useState<TimelineEvent[]>(() => storageService.getRohanMehtaTimeline());

  // Drawers & Modals
  const [activeEvidence, setActiveEvidence] = useState<EvidenceRecord | null>(null);
  const [isEvidenceDrawerOpen, setIsEvidenceDrawerOpen] = useState(false);
  const [isCaseModalOpen, setIsCaseModalOpen] = useState(false);
  const [caseToEdit, setCaseToEdit] = useState<Case | null>(null);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // User feedback toast
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3200);
  };

  const refreshData = () => {
    setCases(storageService.getCases());
    setPersons(storageService.getPersons());
    setAllEvidence(storageService.getAllEvidence());
    setTimeline(storageService.getRohanMehtaTimeline());
  };

  // 1. Hash Routing Sync (#home, #dash, #p/P-0427, #case/CASE-014, #graph)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.toLowerCase();
      if (hash === '#dash' || hash === '#investigations') {
        setCurrentView('DASHBOARD');
      } else if (hash.startsWith('#p/')) {
        const pid = window.location.hash.slice(3).toUpperCase();
        setSelectedPersonId(pid);
        setCurrentView('SUSPECT');
      } else if (hash.startsWith('#case/')) {
        const cid = window.location.hash.slice(6).toUpperCase();
        setSelectedCaseId(cid);
        setCurrentView('CASE');
      } else if (hash === '#graph' || hash === '#intelligence') {
        setCurrentView('GRAPH');
      } else {
        setCurrentView('HERO');
      }
    };

    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleOpenEvidence = (evidenceId: string) => {
    const ev = allEvidence.find(e => e.evidenceId.toLowerCase() === evidenceId.toLowerCase()) 
      || storageService.getEvidenceById(evidenceId);
    if (ev) {
      setActiveEvidence(ev);
      setIsEvidenceDrawerOpen(true);
    } else {
      showToast(`Evidence record ${evidenceId} opened from dossier`);
    }
  };

  const handleNavigate = (view: 'HERO' | 'DASHBOARD' | 'SUSPECT' | 'CASE' | 'GRAPH', entityId?: string) => {
    if (view === 'HERO') {
      window.location.hash = '#home';
    } else if (view === 'DASHBOARD') {
      window.location.hash = '#dash';
    } else if (view === 'SUSPECT') {
      window.location.hash = `#p/${entityId || selectedPersonId}`;
    } else if (view === 'CASE') {
      window.location.hash = `#case/${entityId || selectedCaseId}`;
    } else if (view === 'GRAPH') {
      window.location.hash = '#graph';
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleAddNewCase = () => {
    setCaseToEdit(null);
    setIsCaseModalOpen(true);
  };

  const handleEditCase = (c: Case) => {
    setCaseToEdit(c);
    setIsCaseModalOpen(true);
  };

  const handleCaseSaved = (savedCase: Case) => {
    refreshData();
    setSelectedCaseId(savedCase.id);
    showToast(`Case ${savedCase.id} ("${savedCase.title}") saved successfully`);
  };

  const handleDataReset = () => {
    refreshData();
    setSelectedPersonId('P-0427');
    setSelectedCaseId('CASE-014');
    window.location.hash = '#home';
    showToast('KRONOS demonstration records restored to factory defaults');
  };

  // Find active entity objects
  const currentCase = cases.find(c => c.id === selectedCaseId) || cases[0];
  const currentPerson = persons.find(p => p.id === selectedPersonId) || persons[0];

  return (
    <div className="min-h-screen bg-[#F2E9DA] text-[#30251F] font-sans relative selection:bg-[#B96D50]/20 selection:text-[#30251F]">
      {/* 3. The Fixed Background (Grain, Jaali Diamond Lattice, Corner Rings, Seeded Constellation) */}
      <ArchivalBackground />

      {/* Top Floating Navigation Bar */}
      <Navigation
        currentView={currentView}
        onNavigate={handleNavigate}
        onOpenEvidence={handleOpenEvidence}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenNotifications={() => setIsNotificationOpen(true)}
      />

      {/* Main Content Area (z-index 1 above fixed SVG background) */}
      <main className="w-full relative z-[1]">
        {currentView === 'HERO' && (
          <HeroExperience
            onEnterDashboard={() => handleNavigate('DASHBOARD')}
            onExplorePerson={() => handleNavigate('SUSPECT', 'P-0427')}
            onExploreNetwork={() => handleNavigate('GRAPH')}
          />
        )}

        {currentView === 'DASHBOARD' && (
          <SignatureDashboard
            cases={cases}
            persons={persons}
            selectedCaseId={selectedCaseId}
            selectedPersonId={selectedPersonId}
            onSelectCase={cid => setSelectedCaseId(cid)}
            onSelectPerson={pid => setSelectedPersonId(pid)}
            onOpenCaseWorkspace={cid => handleNavigate('CASE', cid)}
            onOpenSuspectDossier={pid => handleNavigate('SUSPECT', pid)}
            onAddNewCase={handleAddNewCase}
          />
        )}

        {currentView === 'SUSPECT' && (
          <SuspectProfile
            person={currentPerson}
            timeline={timeline}
            onBack={() => handleNavigate('DASHBOARD')}
            onOpenCase={cid => handleNavigate('CASE', cid)}
            onOpenEvidence={handleOpenEvidence}
            onViewGraph={pid => handleNavigate('GRAPH', pid)}
          />
        )}

        {currentView === 'CASE' && (
          <CaseWorkspace
            currentCase={currentCase}
            allPersons={persons}
            evidenceList={allEvidence.filter(e => e.caseId === currentCase.id || currentCase.evidenceIds.includes(e.evidenceId))}
            onBack={() => handleNavigate('DASHBOARD')}
            onOpenPerson={pid => handleNavigate('SUSPECT', pid)}
            onOpenEvidence={handleOpenEvidence}
            onEditCase={handleEditCase}
          />
        )}

        {currentView === 'GRAPH' && (
          <ThreeRelationshipGraph
            initialFocusId={selectedPersonId}
            onOpenPerson={pid => handleNavigate('SUSPECT', pid)}
            onOpenCase={cid => handleNavigate('CASE', cid)}
            onOpenEvidence={handleOpenEvidence}
            onBack={() => handleNavigate('DASHBOARD')}
          />
        )}
      </main>

      {/* Slide-out Evidence Detail Drawer */}
      <EvidenceDrawer
        evidence={activeEvidence}
        isOpen={isEvidenceDrawerOpen}
        onClose={() => setIsEvidenceDrawerOpen(false)}
        onOpenCase={cid => {
          setIsEvidenceDrawerOpen(false);
          handleNavigate('CASE', cid);
        }}
        onOpenPerson={pid => {
          setIsEvidenceDrawerOpen(false);
          handleNavigate('SUSPECT', pid);
        }}
      />

      {/* Case Creation / Edit Modal */}
      <CaseModal
        isOpen={isCaseModalOpen}
        onClose={() => setIsCaseModalOpen(false)}
        onCaseSaved={handleCaseSaved}
        caseToEdit={caseToEdit}
        availablePersons={persons}
      />

      {/* Notifications Drawer */}
      <NotificationDrawer
        isOpen={isNotificationOpen}
        onClose={() => setIsNotificationOpen(false)}
        onNavigateToTarget={(targetType, targetId) => {
          if (targetType === 'PERSON') {
            handleNavigate('SUSPECT', targetId);
          } else if (targetType === 'CASE') {
            handleNavigate('CASE', targetId);
          } else if (targetType === 'EVIDENCE') {
            handleOpenEvidence(targetId);
          }
        }}
      />

      {/* Settings & Reset Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onDataReset={handleDataReset}
      />

      {/* Global Interactive Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#30251F] text-[#F8F3E9] px-4 py-3 rounded-xl shadow-2xl border border-[#C69A55]/40 flex items-center gap-2.5 font-mono text-xs animate-slide-left">
          <CheckCircle2 className="w-4 h-4 text-[#C69A55] shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
};
