import React, { useState } from 'react';
import { 
  X, 
  Bell, 
  AlertTriangle, 
  ShieldAlert, 
  Radio, 
  CreditCard, 
  CheckCheck,
  ExternalLink,
  Clock
} from 'lucide-react';

interface AlertItem {
  id: string;
  type: 'SIM_SWAP' | 'FINANCIAL_SURGE' | 'RENDEZVOUS' | 'NEW_DEVICE';
  title: string;
  description: string;
  timestamp: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  read: boolean;
  targetType: 'PERSON' | 'CASE' | 'EVIDENCE';
  targetId: string;
}

const INITIAL_ALERTS: AlertItem[] = [
  {
    id: 'ALT-901',
    type: 'SIM_SWAP',
    title: 'IMSI Swap / Burner Activation',
    description: 'Hardware IMEI associated with Rohan Mehta (P-0427) registered a new prepaid SIM card at Ambala Cantt Tower #4.',
    timestamp: '14 mins ago',
    severity: 'CRITICAL',
    read: false,
    targetType: 'PERSON',
    targetId: 'P-0427'
  },
  {
    id: 'ALT-902',
    type: 'FINANCIAL_SURGE',
    title: 'High-Velocity RTGS Surge',
    description: 'Split transactions totaling ₹12,50,000 cleared through Golden Horizon Logistics account ACC-7721 in CASE-014.',
    timestamp: '1 hour ago',
    severity: 'CRITICAL',
    read: false,
    targetType: 'CASE',
    targetId: 'CASE-014'
  },
  {
    id: 'ALT-903',
    type: 'RENDEZVOUS',
    title: 'Cross-Case Rendezvous Detected',
    description: 'Spatial co-location flagged: P-0427 and Vikramjit Sethi (P-0299) triangulated within 250m radius at Aerocity Transit Hub.',
    timestamp: '3 hours ago',
    severity: 'WARNING',
    read: false,
    targetType: 'PERSON',
    targetId: 'P-0427'
  },
  {
    id: 'ALT-904',
    type: 'NEW_DEVICE',
    title: 'Forensic Extraction Logged',
    description: 'Cryptographic hash verified for seized iPhone 14 Pro (DEV-8821) chain-of-custody archive.',
    timestamp: 'Yesterday',
    severity: 'INFO',
    read: true,
    targetType: 'EVIDENCE',
    targetId: 'EVD-0427-02'
  }
];

interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateToTarget: (targetType: 'PERSON' | 'CASE' | 'EVIDENCE', targetId: string) => void;
}

export const NotificationDrawer: React.FC<NotificationDrawerProps> = ({
  isOpen,
  onClose,
  onNavigateToTarget
}) => {
  const [alerts, setAlerts] = useState<AlertItem[]>(INITIAL_ALERTS);

  if (!isOpen) return null;

  const markAllRead = () => {
    setAlerts(alerts.map(a => ({ ...a, read: true })));
  };

  const handleAlertClick = (alert: AlertItem) => {
    setAlerts(alerts.map(a => a.id === alert.id ? { ...a, read: true } : a));
    onClose();
    onNavigateToTarget(alert.targetType, alert.targetId);
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return 'bg-[#B96D50]/15 text-[#B96D50] border-[#B96D50]/30';
      case 'WARNING': return 'bg-[#C69A55]/15 text-[#C69A55] border-[#C69A55]/30';
      default: return 'bg-[#7B8062]/15 text-[#7B8062] border-[#7B8062]/30';
    }
  };

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'SIM_SWAP': return <Radio className="w-4 h-4 text-[#B96D50]" />;
      case 'FINANCIAL_SURGE': return <CreditCard className="w-4 h-4 text-[#C69A55]" />;
      case 'RENDEZVOUS': return <ShieldAlert className="w-4 h-4 text-[#B96D50]" />;
      default: return <AlertTriangle className="w-4 h-4 text-[#7B8062]" />;
    }
  };

  const unreadCount = alerts.filter(a => !a.read).length;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-sm flex justify-end animate-fade-in font-sans">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full max-w-md bg-[#FAF6F0] h-full shadow-2xl border-l border-[#DCCAB0] flex flex-col z-10 animate-slide-left">
        {/* Header */}
        <div className="p-5 border-b border-[#DCCAB0] bg-[#F5EFEB] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#B96D50]/15 text-[#B96D50] relative">
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#B96D50] animate-pulse" />
              )}
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-[#30251F]">
                Intelligence Dispatch
              </h3>
              <p className="text-xs text-[#A86F45] font-mono">
                {unreadCount} unread automated heuristic alerts
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

        {/* Filter / Mark Read Subheader */}
        <div className="px-5 py-2.5 bg-[#FBF8F3] border-b border-[#DCCAB0] flex items-center justify-between text-xs">
          <span className="font-mono text-[#7B8062] text-[11px]">Real-time Heuristic Monitor</span>
          {unreadCount > 0 && (
            <button
              onClick={markAllRead}
              className="font-mono text-[11px] text-[#A86F45] hover:text-[#B96D50] flex items-center gap-1 transition-colors"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              Mark all as read
            </button>
          )}
        </div>

        {/* Alerts List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {alerts.map(alert => (
            <div
              key={alert.id}
              onClick={() => handleAlertClick(alert)}
              className={`p-4 rounded-xl border transition-all cursor-pointer ${
                alert.read 
                  ? 'bg-[#FAF6F0] border-[#DCCAB0]/60 opacity-80 hover:opacity-100 hover:bg-[#F5EFEB]' 
                  : 'bg-[#FBF8F3] border-[#B96D50]/40 shadow-sm hover:border-[#B96D50] hover:bg-[#F5EFEB]'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-md bg-[#F5EFEB] border border-[#DCCAB0]/50">
                    {getAlertIcon(alert.type)}
                  </div>
                  <h4 className="font-serif text-sm font-bold text-[#30251F]">
                    {alert.title}
                  </h4>
                </div>
                <span className={`px-2 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider border font-bold ${getSeverityBadge(alert.severity)}`}>
                  {alert.severity}
                </span>
              </div>

              <p className="text-xs text-[#433A32]/85 leading-relaxed pl-8 mb-2">
                {alert.description}
              </p>

              <div className="flex items-center justify-between text-[10px] font-mono pl-8 text-[#A86F45]">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {alert.timestamp}
                </span>
                <span className="flex items-center gap-1 font-semibold text-[#B96D50] hover:underline">
                  Inspect {alert.targetType}: {alert.targetId}
                  <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#DCCAB0] bg-[#F5EFEB] text-center text-[11px] font-mono text-[#7B8062]">
          KRONOS Automated Intelligence Engine • Local Simulator Active
        </div>
      </div>
    </div>
  );
};

