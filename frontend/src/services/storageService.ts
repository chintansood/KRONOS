import { Case, Person, EvidenceRecord, TimelineEvent } from '../types/investigation';
import { INITIAL_CASES, INITIAL_PERSONS, INITIAL_EVIDENCE, ROHAN_MEHTA_TIMELINE } from '../data/mockData';

const STORAGE_KEYS = {
  CASES: 'kr_cases',
  PERSONS: 'kr_persons',
  EVIDENCE: 'kr_evidence',
  BOOKMARKS: 'kr_bm',
  SEARCH_HISTORY: 'kr_search',
  NOTIFICATIONS: 'kr_notifications',
};

export const storageService = {
  getCases(): Case[] {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.CASES);
      return data ? JSON.parse(data) : INITIAL_CASES;
    } catch {
      return INITIAL_CASES;
    }
  },

  saveCases(cases: Case[]): void {
    try {
      localStorage.setItem(STORAGE_KEYS.CASES, JSON.stringify(cases));
    } catch (e) {
      console.warn('Failed to save cases to localStorage', e);
    }
  },

  getCaseById(id: string): Case | undefined {
    return this.getCases().find(c => c.id.toLowerCase() === id.toLowerCase());
  },

  addOrUpdateCase(caseData: Partial<Case> & { title: string }): Case {
    const cases = this.getCases();
    const existingIndex = cases.findIndex(c => c.id === caseData.id);
    
    if (existingIndex >= 0) {
      const updated: Case = {
        ...cases[existingIndex],
        ...caseData,
        lastActivity: 'Just now'
      };
      cases[existingIndex] = updated;
      this.saveCases(cases);
      return updated;
    } else {
      const newId = caseData.id || `CASE-${String(cases.length + 1).padStart(3, '0')}`;
      const newCase: Case = {
        id: newId,
        title: caseData.title,
        offenceCategory: caseData.offenceCategory || 'Financial Fraud',
        description: caseData.description || 'Newly initiated investigative case dossier.',
        status: caseData.status || 'ACTIVE',
        priority: caseData.priority || 'MEDIUM',
        firNumber: caseData.firNumber || `FIR-2025-${String(cases.length + 1).padStart(4, '0')}`,
        policeStation: caseData.policeStation || 'PS-CENTRAL',
        district: caseData.district || 'Chandigarh',
        incidentDate: caseData.incidentDate || new Date().toISOString().slice(0, 16).replace('T', ' '),
        registrationDate: caseData.registrationDate || new Date().toISOString().slice(0, 16).replace('T', ' '),
        reportingDelayHours: caseData.reportingDelayHours || 24.0,
        totalFinancialVolume: caseData.totalFinancialVolume || 500000,
        peopleCount: caseData.peopleCount || 2,
        evidenceCount: caseData.evidenceCount || 1,
        lastActivity: 'Just created',
        leadInvestigator: caseData.leadInvestigator || 'Investigating Officer',
        personIds: caseData.personIds || ['P-0427'],
        primarySuspectIds: caseData.primarySuspectIds || [],
        evidenceIds: caseData.evidenceIds || ['EVID-014-001'],
        isCustom: true
      };
      cases.unshift(newCase);
      this.saveCases(cases);
      return newCase;
    }
  },

  getPersons(): Person[] {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.PERSONS);
      return data ? JSON.parse(data) : INITIAL_PERSONS;
    } catch {
      return INITIAL_PERSONS;
    }
  },

  getPersonById(id: string): Person | undefined {
    return this.getPersons().find(p => p.id.toLowerCase() === id.toLowerCase());
  },

  getTimelineForPerson(personId: string): TimelineEvent[] {
    if (personId.toUpperCase() === 'P-0427') {
      return ROHAN_MEHTA_TIMELINE;
    }
    // Generate tailored timeline for other persons
    const person = this.getPersonById(personId);
    if (!person) return ROHAN_MEHTA_TIMELINE;

    return [
      {
        id: `EVT-${person.id}-01`,
        timestamp: `${person.firstAppearance} 10:00:00`,
        dateStr: person.firstAppearance,
        monthStr: person.firstAppearance.slice(3, 6).toUpperCase(),
        timeStr: '10:00',
        modality: 'FIR',
        title: `Named in Initial Crime Dossier — ${person.caseIds[0] || 'CASE-001'}`,
        description: `Mentioned in police report filed at ${person.knownLocations[0] || 'State Police Station'}. Evidence points to coordinated syndication.`,
        caseId: person.caseIds[0] || 'CASE-001',
        evidenceId: 'EVID-014-001',
        locationName: person.knownLocations[0] || 'Central District',
        severity: 'CRITICAL'
      },
      {
        id: `EVT-${person.id}-02`,
        timestamp: '18 Feb 2025 14:22:00',
        dateStr: '18 Feb 2025',
        monthStr: 'FEB',
        timeStr: '14:22',
        modality: 'COMMUNICATION',
        title: 'Communication Intercept — Encrypted Channel',
        description: `Recorded call transmission linking ${person.name} (${person.contactNumbers[0]}) to primary coordinator P-0299.`,
        caseId: person.caseIds[1] || person.caseIds[0] || 'CASE-001',
        evidenceId: 'EVID-014-002',
        counterpartyId: 'P-0299',
        deviceOrHardwareId: person.associatedDevices[0] || 'DEV-GENERIC',
        severity: 'SUSPICIOUS'
      },
      {
        id: `EVT-${person.id}-03`,
        timestamp: `${person.latestActivity} 17:45:00`,
        dateStr: person.latestActivity,
        monthStr: person.latestActivity.slice(3, 6).toUpperCase(),
        timeStr: '17:45',
        modality: 'FINANCIAL',
        title: 'High-Velocity Outbound Transaction Sweep',
        description: `Banking activity recorded from account ${person.bankAccounts[0] || 'BANK-MULE'}. Dispersal into ancillary mule accounts.`,
        caseId: person.caseIds[0] || 'CASE-001',
        evidenceId: 'EVID-017-002',
        amount: 325000,
        severity: 'CRITICAL',
        isAnomaly: true,
        anomalyType: 'FINANCIAL_SURGE'
      }
    ];
  },

  getRohanMehtaTimeline(): TimelineEvent[] {
    return this.getTimelineForPerson('P-0427');
  },

  getAllEvidence(): EvidenceRecord[] {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.EVIDENCE);
      return data ? JSON.parse(data) : INITIAL_EVIDENCE;
    } catch {
      return INITIAL_EVIDENCE;
    }
  },

  getEvidenceById(id: string): EvidenceRecord | undefined {
    return this.getAllEvidence().find(e => e.evidenceId.toLowerCase() === id.toLowerCase());
  },

  getBookmarks(): string[] {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.BOOKMARKS);
      return data ? JSON.parse(data) : ['P-0427', 'CASE-014'];
    } catch {
      return ['P-0427', 'CASE-014'];
    }
  },

  toggleBookmark(id: string): boolean {
    const bookmarks = this.getBookmarks();
    const idx = bookmarks.indexOf(id);
    let isBookmarked = false;
    if (idx >= 0) {
      bookmarks.splice(idx, 1);
    } else {
      bookmarks.push(id);
      isBookmarked = true;
    }
    localStorage.setItem(STORAGE_KEYS.BOOKMARKS, JSON.stringify(bookmarks));
    return isBookmarked;
  },

  isBookmarked(id: string): boolean {
    return this.getBookmarks().includes(id);
  },

  getSearchHistory(): string[] {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.SEARCH_HISTORY);
      return data ? JSON.parse(data) : ['Rohan Mehta', 'CASE-014', 'Ambala', 'Hawala Syndicate', 'P-0299'];
    } catch {
      return ['Rohan Mehta', 'CASE-014'];
    }
  },

  addSearchQuery(q: string): void {
    if (!q || !q.trim()) return;
    const history = this.getSearchHistory().filter(item => item.toLowerCase() !== q.toLowerCase());
    history.unshift(q.trim());
    localStorage.setItem(STORAGE_KEYS.SEARCH_HISTORY, JSON.stringify(history.slice(0, 10)));
  },

  resetDemoData(): void {
    try {
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith('kr_')) {
          localStorage.removeItem(key);
        }
      });
    } catch (e) {
      console.warn('Error clearing localStorage', e);
    }
  }
};
