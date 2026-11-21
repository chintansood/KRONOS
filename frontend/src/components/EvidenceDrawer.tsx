import React from 'react';
import { 
  X, 
  FileText, 
  Calendar, 
  MapPin, 
  ShieldCheck, 
  User, 
  FolderKanban, 
  Download, 
  ExternalLink,
  Layers,
  Hash,
  AlertTriangle
} from 'lucide-react';
import { EvidenceRecord } from '../types/investigation';
import { exportService } from '../services/exportService';

interface EvidenceDrawerProps {
  evidence: EvidenceRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenCase: (caseId: string) => void;
  onOpenPerson: (personId: string) => void;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  evidence,
  isOpen,
  onClose,
  onOpenCase,
  onOpenPerson
}) => {
  if (!isOpen || !evidence) return null;

  const handleExportJson = () => {
    exportService.exportEvidenceAsJson(evidence);
  };

  const getModalityColor = (modality: string) => {
    switch (modality) {
      case 'FIR': return 'bg-[#B96D50]/15 text-[#B96D50] border-[#B96D50]/30';
      case 'COMMUNICATION': return 'bg-[#5B7B94]/15 text-[#5B7B94] border-[#5B7B94]/30';
      case 'LOCATION': return 'bg-[#7B8062]/15 text-[#7B8062] border-[#7B8062]/30';
      case 'FINANCIAL': return 'bg-[#A86F45]/15 text-[#A86F45] border-[#A86F45]/30';
      case 'CROSS_CASE': return 'bg-[#8E5B84]/15 text-[#8E5B84] border-[#8E5B84]/30';
      default: return 'bg-[#433A32]/15 text-[#433A32] border-[#433A32]/30';
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-sm flex justify-end animate-fade-in">
      {/* Background dismissal backdrop */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Slide-out Drawer Panel */}
      <div className="relative w-full max-w-lg bg-[#FAF6F0] h-full shadow-2xl border-l border-[#DCCAB0] flex flex-col z-10 animate-slide-left font-sans">
        {/* Drawer Header */}
        <div className="p-6 border-b border-[#DCCAB0] bg-[#F5EFEB] flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className={`px-2 py-0.5 rounded text-[11px] font-mono uppercase tracking-wider border font-bold ${getModalityColor(evidence.modality)}`}>
                {evidence.modality}
              </span>
              <span className="font-mono text-xs text-[#A86F45] font-semibold">
                {evidence.evidenceId}
              </span>
            </div>
            <h3 className="font-serif text-xl font-bold text-[#30251F]">
              Investigative Evidence File
            </h3>
            <p className="text-xs text-[#433A32]/70 font-mono mt-0.5">
              Source Record Ref: {evidence.sourceRecordId}
            </p>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[#EAE0D2] text-[#433A32] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drawer Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-[#433A32] text-xs">
          {/* Reliability & Case Badges */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-[#FBF8F3] rounded-lg border border-[#DCCAB0]">
              <div className="text-[10px] uppercase font-mono text-[#A86F45] mb-1 flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-[#7B8062]" />
                Reliability Rating
              </div>
              <div className="font-serif text-sm font-bold text-[#30251F]">
                {evidence.sourceReliability} CONFIDENCE
              </div>
              <div className="text-[10px] text-[#7B8062] mt-0.5">
                Verified through telecom / banking API logs
              </div>
            </div>

            <div 
              onClick={() => {
                onClose();
                onOpenCase(evidence.caseId);
              }}
              className="p-3 bg-[#FBF8F3] rounded-lg border border-[#DCCAB0] hover:border-[#B96D50] cursor-pointer transition-colors group"
            >
              <div className="text-[10px] uppercase font-mono text-[#A86F45] mb-1 flex items-center justify-between">
                <span>Associated Case</span>
                <ExternalLink className="w-3 h-3 text-[#B96D50] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <div className="font-serif text-sm font-bold text-[#B96D50]">
                {evidence.caseId}
              </div>
              <div className="text-[10px] text-[#A86F45] mt-0.5">
                Click to open case workspace
              </div>
            </div>
          </div>

          {/* Timestamp & Location */}
          <div className="p-4 bg-[#FBF8F3] rounded-lg border border-[#DCCAB0] space-y-3">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#A86F45]" />
              <div>
                <span className="font-mono text-[10px] text-[#A86F45] block uppercase">Recorded Timestamp</span>
                <span className="font-mono text-xs font-semibold text-[#30251F]">{evidence.timestamp}</span>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2 border-t border-[#DCCAB0]/50">
              <MapPin className="w-4 h-4 text-[#B96D50]" />
              <div>
                <span className="font-mono text-[10px] text-[#A86F45] block uppercase">Physical / Cell Site Location</span>
                <span className="text-xs font-medium text-[#30251F]">{evidence.locationName}</span>
                {evidence.latitude && evidence.longitude && (
                  <span className="font-mono text-[10px] text-[#7B8062] block mt-0.5">
                    GPS: {evidence.latitude.toFixed(4)}° N, {evidence.longitude.toFixed(4)}° E
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Primary Evidence Narrative */}
          <div>
            <h4 className="font-mono uppercase text-[11px] tracking-wider text-[#A86F45] mb-2 font-semibold flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" />
              Investigative Narrative & Finding
            </h4>
            <div className="p-4 bg-[#FBF8F3] rounded-lg border border-[#DCCAB0] font-serif text-sm leading-relaxed text-[#30251F]">
              {evidence.description}
            </div>
          </div>

          {/* Related Persons of Interest */}
          <div>
            <h4 className="font-mono uppercase text-[11px] tracking-wider text-[#A86F45] mb-2 font-semibold flex items-center gap-1.5">
              <User className="w-3.5 h-3.5" />
              Connected Persons of Interest
            </h4>
            <div className="flex flex-wrap gap-2">
              {evidence.relatedPersonIds.map(pid => (
                <button
                  key={pid}
                  onClick={() => {
                    onClose();
                    onOpenPerson(pid);
                  }}
                  className="px-3 py-1.5 bg-[#F5EFEB] hover:bg-[#EAE0D2] border border-[#DCCAB0] hover:border-[#B96D50] rounded-lg font-mono text-xs text-[#30251F] flex items-center gap-1.5 transition-colors group"
                >
                  <span className="font-bold text-[#B96D50]">{pid}</span>
                  <ExternalLink className="w-3 h-3 text-[#A86F45] opacity-60 group-hover:opacity-100" />
                </button>
              ))}
            </div>
          </div>

          {/* Technical Metadata / Artifact Details */}
          {evidence.metadata && Object.keys(evidence.metadata).length > 0 && (
            <div>
              <h4 className="font-mono uppercase text-[11px] tracking-wider text-[#A86F45] mb-2 font-semibold flex items-center gap-1.5">
                <Hash className="w-3.5 h-3.5" />
                Technical Metadata & Hash Log
              </h4>
              <div className="bg-[#F5EFEB] p-3 rounded-lg border border-[#DCCAB0] overflow-x-auto">
                <table className="w-full text-left font-mono text-[11px]">
                  <tbody>
                    {Object.entries(evidence.metadata).map(([key, val]) => (
                      <tr key={key} className="border-b border-[#DCCAB0]/40 last:border-0">
                        <td className="py-1 text-[#A86F45] font-semibold pr-3 capitalize">{key.replace(/_/g, ' ')}:</td>
                        <td className="py-1 text-[#30251F] font-mono break-all">{String(val)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Action Footer */}
        <div className="p-4 border-t border-[#DCCAB0] bg-[#F5EFEB] flex items-center gap-3">
          <button
            onClick={handleExportJson}
            className="flex-1 py-2.5 px-4 bg-[#FBF8F3] hover:bg-[#EAE0D2] border border-[#DCCAB0] text-[#30251F] rounded-lg font-mono text-xs font-semibold tracking-wider flex items-center justify-center gap-2 transition-colors"
          >
            <Download className="w-4 h-4 text-[#A86F45]" />
            <span>Export Record (JSON)</span>
          </button>
          <button
            onClick={onClose}
            className="py-2.5 px-5 bg-[#30251F] hover:bg-[#433A32] text-[#F8F3E9] rounded-lg font-mono text-xs font-semibold tracking-wider transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

