import React, { useState, useEffect } from 'react';
import { X, FolderPlus, Save, AlertCircle, Check } from 'lucide-react';
import { Case, Person, CasePriority, CaseStatus } from '../types/investigation';
import { storageService } from '../services/storageService';

interface CaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaseSaved: (savedCase: Case) => void;
  caseToEdit?: Case | null;
  availablePersons: Person[];
}

export const CaseModal: React.FC<CaseModalProps> = ({
  isOpen,
  onClose,
  onCaseSaved,
  caseToEdit,
  availablePersons
}) => {
  const [title, setTitle] = useState('');
  const [offenceCategory, setOffenceCategory] = useState('Organized Financial Fraud');
  const [priority, setPriority] = useState<CasePriority>('HIGH');
  const [status, setStatus] = useState<CaseStatus>('ACTIVE');
  const [summary, setSummary] = useState('');
  const [selectedPersonIds, setSelectedPersonIds] = useState<string[]>([]);
  const [primarySuspectId, setPrimarySuspectId] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState('');

  const OFFENCE_CATEGORIES = [
    'Organized Financial Fraud',
    'Cross-Border Hawala & Money Laundering',
    'Narcotics Syndicate & Transit Logistics',
    'Cybercrime & Syndicate Extortion',
    'Counterfeit Currency & Document Forgery',
    'Conspiracy & Racketeering'
  ];

  useEffect(() => {
    if (caseToEdit) {
      setTitle(caseToEdit.title);
      setOffenceCategory(caseToEdit.offenceCategory);
      setPriority(caseToEdit.priority);
      setStatus(caseToEdit.status);
      setSummary(caseToEdit.description || '');
      setSelectedPersonIds(caseToEdit.personIds || []);
      setPrimarySuspectId(caseToEdit.primarySuspectIds?.[0] || '');
    } else {
      // Default blank values for new case
      setTitle('');
      setOffenceCategory('Organized Financial Fraud');
      setPriority('HIGH');
      setStatus('ACTIVE');
      setSummary('');
      setSelectedPersonIds(['P-0427']);
      setPrimarySuspectId('P-0427');
    }
    setErrorMessage('');
  }, [caseToEdit, isOpen]);

  if (!isOpen) return null;

  const handleTogglePerson = (pid: string) => {
    if (selectedPersonIds.includes(pid)) {
      setSelectedPersonIds(selectedPersonIds.filter(id => id !== pid));
      if (primarySuspectId === pid) {
        setPrimarySuspectId('');
      }
    } else {
      setSelectedPersonIds([...selectedPersonIds, pid]);
      if (!primarySuspectId) {
        setPrimarySuspectId(pid);
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMessage('Case title cannot be empty.');
      return;
    }

    const payload: Partial<Case> & { title: string } = {
      id: caseToEdit ? caseToEdit.id : undefined,
      title: title.trim(),
      offenceCategory,
      priority,
      status,
      description: summary.trim(),
      peopleCount: selectedPersonIds.length,
      personIds: selectedPersonIds,
      primarySuspectIds: [primarySuspectId || selectedPersonIds[0] || 'P-0427'],
      evidenceCount: caseToEdit ? caseToEdit.evidenceCount : 3,
      evidenceIds: caseToEdit ? caseToEdit.evidenceIds : ['EVD-0427-01', 'EVD-0427-02'],
      isCustom: true
    };

    const saved = storageService.addOrUpdateCase(payload);
    onCaseSaved(saved);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in font-sans">
      <div className="bg-[#FAF6F0] w-full max-w-2xl rounded-2xl shadow-2xl border border-[#DCCAB0] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="p-5 border-b border-[#DCCAB0] bg-[#F5EFEB] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-[#B96D50]/15 text-[#B96D50]">
              <FolderPlus className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-[#30251F]">
                {caseToEdit ? `Edit Case Docket (${caseToEdit.id})` : 'Register New Investigation Case'}
              </h3>
              <p className="text-xs text-[#A86F45] font-mono">
                SIH-2026 Standalone Local Storage Persistence
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-[#EAE0D2] text-[#433A32] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto flex-1 text-xs text-[#433A32]">
          {errorMessage && (
            <div className="p-3 bg-[#B96D50]/10 border border-[#B96D50]/30 rounded-lg text-[#B96D50] flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Case Title */}
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
              Case Title / Operational Codename *
            </label>
            <input 
              type="text"
              required
              placeholder="e.g. Operation Golden Falcon / Hawala Corridor Transit"
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-[#FBF8F3] border border-[#DCCAB0] rounded-lg font-serif text-sm text-[#30251F] focus:outline-none focus:border-[#B96D50]"
            />
          </div>

          {/* Offence Category & Priority */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
                Offence Category
              </label>
              <select
                value={offenceCategory}
                onChange={e => setOffenceCategory(e.target.value)}
                className="w-full px-3 py-2 bg-[#FBF8F3] border border-[#DCCAB0] rounded-lg font-sans text-xs text-[#30251F] focus:outline-none focus:border-[#B96D50]"
              >
                {OFFENCE_CATEGORIES.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
                Priority Level
              </label>
              <div className="grid grid-cols-4 gap-1.5">
                {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as CasePriority[]).map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPriority(p)}
                    className={`py-1.5 text-[10px] font-mono rounded border transition-colors ${
                      priority === p 
                        ? 'bg-[#B96D50] text-[#F8F3E9] border-[#B96D50] font-bold shadow-sm' 
                        : 'bg-[#FBF8F3] text-[#433A32] border-[#DCCAB0] hover:bg-[#EAE0D2]'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Status */}
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
              Investigation Status
            </label>
            <div className="flex flex-wrap gap-2">
              {(['ACTIVE', 'UNDER_REVIEW', 'CHARGE_SHEETED', 'ARCHIVED'] as CaseStatus[]).map(st => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setStatus(st)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors border ${
                    status === st
                      ? 'bg-[#30251F] text-[#F8F3E9] border-[#30251F] font-semibold'
                      : 'bg-[#FBF8F3] text-[#433A32] border-[#DCCAB0] hover:bg-[#EAE0D2]'
                  }`}
                >
                  {st.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
              Preliminary Briefing / Investigative Notes
            </label>
            <textarea
              rows={3}
              placeholder="Record initial FIR allegations, cross-state jurisdiction details, or key suspect intelligence..."
              value={summary}
              onChange={e => setSummary(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-[#FBF8F3] border border-[#DCCAB0] rounded-lg font-sans text-xs text-[#30251F] focus:outline-none focus:border-[#B96D50]"
            />
          </div>

          {/* Persons Involved Selection */}
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
              Select Persons of Investigative Interest ({selectedPersonIds.length} attached)
            </label>
            <div className="grid grid-cols-2 gap-2 max-h-36 overflow-y-auto p-2 bg-[#F5EFEB] rounded-lg border border-[#DCCAB0]">
              {availablePersons.map(p => {
                const isSelected = selectedPersonIds.includes(p.id);
                return (
                  <div
                    key={p.id}
                    onClick={() => handleTogglePerson(p.id)}
                    className={`p-2 rounded-lg border cursor-pointer transition-all flex items-center justify-between text-xs ${
                      isSelected 
                        ? 'bg-[#FBF8F3] border-[#B96D50] text-[#30251F]' 
                        : 'bg-[#FAF6F0] border-transparent text-[#433A32]/70 hover:bg-[#F5EFEB]'
                    }`}
                  >
                    <div>
                      <span className="font-mono text-[10px] text-[#A86F45] block font-semibold">{p.id}</span>
                      <span className="font-medium text-xs text-[#30251F]">{p.name}</span>
                    </div>
                    {isSelected && (
                      <Check className="w-4 h-4 text-[#B96D50]" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Primary Suspect Dropdown */}
          {selectedPersonIds.length > 0 && (
            <div>
              <label className="block font-mono text-[11px] uppercase tracking-wider text-[#A86F45] font-semibold mb-1">
                Designate Primary Suspect
              </label>
              <select
                value={primarySuspectId}
                onChange={e => setPrimarySuspectId(e.target.value)}
                className="w-full px-3 py-2 bg-[#FBF8F3] border border-[#DCCAB0] rounded-lg font-sans text-xs text-[#30251F] focus:outline-none focus:border-[#B96D50]"
              >
                {selectedPersonIds.map(pid => {
                  const p = availablePersons.find(item => item.id === pid);
                  return (
                    <option key={pid} value={pid}>
                      {pid} — {p?.name || 'Unknown'}
                    </option>
                  );
                })}
              </select>
            </div>
          )}
        </form>

        {/* Modal Footer */}
        <div className="p-4 border-t border-[#DCCAB0] bg-[#F5EFEB] flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-[#DCCAB0] bg-[#FAF6F0] hover:bg-[#EAE0D2] text-[#433A32] rounded-lg font-mono text-xs transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="px-5 py-2 bg-[#B96D50] hover:bg-[#A86F45] text-[#F8F3E9] rounded-lg font-serif text-sm font-semibold tracking-wide shadow flex items-center gap-2 transition-colors"
          >
            <Save className="w-4 h-4" />
            <span>{caseToEdit ? 'Save Modifications' : 'Create Case Docket'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
