import React, { useState } from 'react';
import { 
  X, 
  Settings, 
  RotateCcw, 
  ShieldCheck, 
  Sliders, 
  Cpu, 
  Check, 
  AlertTriangle,
  FileCheck
} from 'lucide-react';
import { storageService } from '../services/storageService';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDataReset: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  onDataReset
}) => {
  const [resetConfirmed, setResetConfirmed] = useState(false);
  const [motionSpeed, setMotionSpeed] = useState<'standard' | 'cinematic' | 'reduced'>('standard');
  const [hapticFeedback, setHapticFeedback] = useState(true);

  if (!isOpen) return null;

  const handleReset = () => {
    storageService.resetDemoData();
    setResetConfirmed(true);
    setTimeout(() => {
      onDataReset();
      onClose();
      setResetConfirmed(false);
    }, 900);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in font-sans">
      <div className="bg-[#FAF6F0] w-full max-w-xl rounded-2xl shadow-2xl border border-[#DCCAB0] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-[#DCCAB0] bg-[#F5EFEB] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#30251F] text-[#F8F3E9]">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-[#30251F]">
                KRONOS System Configuration
              </h3>
              <p className="text-xs text-[#A86F45] font-mono">
                SIH-2026 Problem Statement 26189 Demonstration Suite
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

        {/* Content */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1 text-xs text-[#433A32]">
          {/* Demo Mode Notice */}
          <div className="p-4 bg-[#FBF8F3] rounded-xl border border-[#DCCAB0] flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-[#7B8062] shrink-0 mt-0.5" />
            <div>
              <h4 className="font-serif text-sm font-bold text-[#30251F] mb-1">
                Zero-Leakage Standalone Architecture
              </h4>
              <p className="text-xs text-[#433A32]/80 leading-relaxed">
                This deployment operates strictly as a self-contained, client-side digital investigation workstation. No external API keys or remote cloud databases are queried. All case docket creation, suspect bookmarking, and investigative analyses persist securely in your local browser sandbox.
              </p>
            </div>
          </div>

          {/* Motion & Interaction Settings */}
          <div>
            <h4 className="font-mono uppercase text-[11px] tracking-wider text-[#A86F45] font-semibold mb-3 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5" />
              Interface Dynamics & Motion
            </h4>
            <div className="grid grid-cols-3 gap-2">
              {[
                { key: 'standard', label: 'Standard Flow', sub: 'Balanced smooth choreography' },
                { key: 'cinematic', label: 'Cinematic', sub: 'Enhanced Three.js particle speeds' },
                { key: 'reduced', label: 'Subtle / Clean', sub: 'Minimal motion & instant cuts' }
              ].map(opt => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setMotionSpeed(opt.key as any)}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    motionSpeed === opt.key 
                      ? 'bg-[#30251F] text-[#F8F3E9] border-[#30251F] shadow-sm' 
                      : 'bg-[#FBF8F3] text-[#433A32] border-[#DCCAB0] hover:bg-[#EAE0D2]'
                  }`}
                >
                  <div className="font-serif text-xs font-bold mb-0.5">{opt.label}</div>
                  <div className={`text-[10px] ${motionSpeed === opt.key ? 'text-[#DCCAB0]' : 'text-[#7B8062]'}`}>
                    {opt.sub}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Problem Statement Citation */}
          <div className="p-4 bg-[#F5EFEB] rounded-xl border border-[#DCCAB0] space-y-2">
            <div className="flex items-center gap-2 text-[#A86F45]">
              <FileCheck className="w-4 h-4" />
              <span className="font-mono text-[11px] font-bold uppercase tracking-wider">
                Hackathon Scope Specifications
              </span>
            </div>
            <p className="text-xs text-[#433A32]/90 leading-relaxed font-sans">
              <strong>Domain:</strong> Multimodal Criminal Network Graph Analytics, Cross-Case Entity Resolution, Temporal Timeline Reconstruction (CDR, Financial, Location, FIR records).
            </p>
            <div className="font-mono text-[10px] text-[#7B8062] pt-1 border-t border-[#DCCAB0]/50">
              KRONOS Engine Version: 2.4.0-standalone • Ready for Evaluation
            </div>
          </div>

          {/* Reset Demo Data Action */}
          <div className="p-4 bg-[#B96D50]/5 rounded-xl border border-[#B96D50]/20 flex items-center justify-between">
            <div>
              <h5 className="font-serif text-xs font-bold text-[#30251F]">
                Reset Demonstration Records
              </h5>
              <p className="text-[11px] text-[#433A32]/70 mt-0.5">
                Restores original case dossiers, Rohan Mehta timeline, and clears local search logs.
              </p>
            </div>
            <button
              onClick={handleReset}
              disabled={resetConfirmed}
              className="px-3.5 py-2 bg-[#B96D50] hover:bg-[#A86F45] text-white rounded-lg font-mono text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50 shrink-0"
            >
              {resetConfirmed ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Resetting...</span>
                </>
              ) : (
                <>
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Restore Defaults</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#DCCAB0] bg-[#F5EFEB] flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-[#30251F] hover:bg-[#433A32] text-[#F8F3E9] rounded-lg font-mono text-xs font-semibold tracking-wider transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

