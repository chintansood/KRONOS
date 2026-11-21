export type Modality = 'CDR' | 'COMMUNICATION' | 'FINANCIAL' | 'LOCATION' | 'FIR' | 'CROSS_CASE';

export type CaseStatus = 'ACTIVE' | 'UNDER_REVIEW' | 'CHARGE_SHEETED' | 'ARCHIVED';
export type CasePriority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type SourceReliability = 'HIGH' | 'MEDIUM' | 'LOW';
export type PersonRole = 'PRIMARY_SUSPECT' | 'CO_ACCUSED' | 'ASSOCIATE' | 'PERSON_OF_INTEREST' | 'COMPLAINANT';

export interface EvidenceRecord {
  evidenceId: string;
  sourceRecordId: string;
  caseId: string;
  modality: Modality;
  timestamp: string;
  locationName: string;
  latitude?: number;
  longitude?: number;
  sourceReliability: SourceReliability;
  description: string;
  relatedPersonIds: string[];
  metadata?: Record<string, any>;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  dateStr: string;
  monthStr: string;
  timeStr: string;
  modality: Modality;
  title: string;
  description: string;
  caseId: string;
  evidenceId: string;
  locationName?: string;
  latitude?: number;
  longitude?: number;
  amount?: number;
  counterpartyId?: string;
  deviceOrHardwareId?: string;
  severity?: 'NORMAL' | 'SUSPICIOUS' | 'CRITICAL';
  isAnomaly?: boolean;
  anomalyType?: 'IMPOSSIBLE_TRAVEL' | 'RENDEZVOUS' | 'BURST' | 'FINANCIAL_SURGE';
}

export interface Person {
  id: string;
  name: string;
  alias?: string;
  role: PersonRole;
  avatarUrl?: string;
  contactNumbers: string[];
  associatedDevices: string[];
  bankAccounts: string[];
  firstAppearance: string;
  latestActivity: string;
  casesMentionedCount: number;
  primarySuspectCasesCount: number;
  caseIds: string[];
  primaryCaseIds: string[];
  casesMentioned: string[];
  primarySuspectCases: string[];
  associatedPersonIds: string[];
  knownLocations: string[];
  notes?: string;
}

export interface Case {
  id: string;
  title: string;
  offenceCategory: string;
  description: string;
  status: CaseStatus;
  priority: CasePriority;
  firNumber: string;
  policeStation: string;
  district: string;
  incidentDate: string;
  registrationDate: string;
  reportingDelayHours: number;
  totalFinancialVolume: number;
  peopleCount: number;
  evidenceCount: number;
  lastActivity: string;
  leadInvestigator: string;
  personIds: string[];
  primarySuspectIds: string[];
  evidenceIds: string[];
  isCustom?: boolean;
}

export interface ChatMessage {
  id: string;
  sender: 'USER' | 'KRONOS_AI';
  mode: 'ASSISTANCE' | 'DETECTIVE';
  text: string;
  timestamp: string;
  referencedEventIds?: string[];
  referencedEvidenceIds?: string[];
  referencedCaseIds?: string[];
  referencedPersonIds?: string[];
  isAnalyticalHypothesis?: boolean;
}

export interface GraphNode {
  id: string;
  label: string;
  sublabel?: string;
  type: 'PERSON' | 'CASE' | 'DEVICE' | 'ACCOUNT' | 'LOCATION' | 'EVIDENCE';
  role?: string;
  val?: number;
  color?: string;
  x?: number;
  y?: number;
  z?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label?: string;
  modality?: Modality;
  weight?: number;
  isAnomaly?: boolean;
}

export interface IntelligenceMetric {
  label: string;
  value: number | string;
  subtext: string;
  filterKey?: string;
}

