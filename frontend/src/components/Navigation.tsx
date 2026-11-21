import React, { useState, useEffect } from 'react';
import { Search, Bell, Bookmark, X, User } from 'lucide-react';
import { storageService } from '../services/storageService';

interface NavigationProps {
  currentView: 'HERO' | 'DASHBOARD' | 'SUSPECT' | 'CASE' | 'GRAPH';
  onNavigate: (view: 'HERO' | 'DASHBOARD' | 'SUSPECT' | 'CASE' | 'GRAPH', entityId?: string) => void;
  onOpenEvidence: (evidenceId: string) => void;
  onOpenSettings: () => void;
  onOpenNotifications: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentView,
  onNavigate,
  onOpenEvidence,
  onOpenSettings,
  onOpenNotifications
}) => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [bookmarksOpen, setBookmarksOpen] = useState(false);
  const [scrolledPastHero, setScrolledPastHero] = useState(false);

  const bookmarks = storageService.getBookmarks();
  const searchHistory = storageService.getSearchHistory();

  // Scroll detection for home page wordmark: appears once scrolled past 1.2 screen heights
  useEffect(() => {
    const handleScroll = () => {
      if (currentView === 'HERO') {
        setScrolledPastHero(window.scrollY > window.innerHeight * 1.2);
      } else {
        setScrolledPastHero(true);
      }
    };

    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [currentView]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    storageService.addSearchQuery(searchQuery);

    const q = searchQuery.toLowerCase();
    const cases = storageService.getCases();
    const persons = storageService.getPersons();

    const matchedPerson = persons.find(p => p.id.toLowerCase().includes(q) || p.name.toLowerCase().includes(q));
    if (matchedPerson) {
      onNavigate('SUSPECT', matchedPerson.id);
      setSearchOpen(false);
      return;
    }

    const matchedCase = cases.find(c => c.id.toLowerCase().includes(q) || c.title.toLowerCase().includes(q) || c.offenceCategory.toLowerCase().includes(q));
    if (matchedCase) {
      onNavigate('CASE', matchedCase.id);
      setSearchOpen(false);
      return;
    }

    onNavigate('DASHBOARD');
    setSearchOpen(false);
  };

  return (
    <>
      <header className="fixed top-0 left-0 right-0 z-40 w-full px-6 py-4 flex items-center justify-between backdrop-blur-md bg-[#F2E9DA]/85 border-b border-[#A86F45]/20 font-sans transition-all">
        {/* Left Column: KRONOS Wordmark (hidden on home until scrolled past 1.2 vh) */}
        <div className="flex items-center min-w-[200px]">
          <button
            onClick={() => onNavigate('HERO')}
            className={`flex items-center gap-2.5 transition-opacity duration-300 focus:outline-none ${
              currentView === 'HERO' && !scrolledPastHero ? 'opacity-0 pointer-events-none' : 'opacity-100'
            }`}
          >
            <div className="w-7 h-7 rounded-full border border-[#A86F45] flex items-center justify-center relative">
              <span className="w-2 h-2 rounded-full bg-[#B96D50]"></span>
            </div>
            <span className="font-serif tracking-[0.2em] text-base font-bold text-[#30251F]">
              KRONOS
            </span>
          </button>
        </div>

        {/* Middle Column: Links (HOME, INVESTIGATIONS, INTELLIGENCE, EVIDENCE, TIMELINE) */}
        <nav className="hidden md:flex items-center space-x-6 text-[12px] font-sans font-medium tracking-[0.14em] uppercase text-[#433A32]">
          <button
            onClick={() => onNavigate('HERO')}
            className={`transition-colors pb-1 ${
              currentView === 'HERO'
                ? 'text-[#30251F] border-b-2 border-[#B96D50] font-semibold'
                : 'hover:text-[#B96D50]'
            }`}
          >
            HOME
          </button>
          <button
            onClick={() => onNavigate('DASHBOARD')}
            className={`transition-colors pb-1 ${
              currentView === 'DASHBOARD'
                ? 'text-[#30251F] border-b-2 border-[#B96D50] font-semibold'
                : 'hover:text-[#B96D50]'
            }`}
          >
            INVESTIGATIONS
          </button>
          <button
            onClick={() => onNavigate('GRAPH')}
            className={`transition-colors pb-1 ${
              currentView === 'GRAPH'
                ? 'text-[#30251F] border-b-2 border-[#B96D50] font-semibold'
                : 'hover:text-[#B96D50]'
            }`}
          >
            INTELLIGENCE
          </button>
          <button
            onClick={() => onOpenEvidence('EVD-0427-01')}
            className="hover:text-[#B96D50] transition-colors pb-1"
          >
            EVIDENCE
          </button>
          <button
            onClick={() => onNavigate('SUSPECT', 'P-0427')}
            className={`transition-colors pb-1 ${
              currentView === 'SUSPECT'
                ? 'text-[#30251F] border-b-2 border-[#B96D50] font-semibold'
                : 'hover:text-[#B96D50]'
            }`}
          >
            TIMELINE
          </button>
        </nav>

        {/* Right Column: DEMO MODE pill, Bell, Avatar */}
        <div className="flex items-center space-x-3 min-w-[200px] justify-end">
          {/* Quick Search Trigger */}
          <button
            onClick={() => setSearchOpen(true)}
            className="p-2 rounded-full hover:bg-[#DCCAB0]/40 text-[#433A32] transition-colors"
            title="Global Search"
          >
            <Search className="w-4 h-4" />
          </button>

          {/* Bookmarks Toggle */}
          <button
            onClick={() => setBookmarksOpen(true)}
            className="p-2 rounded-full hover:bg-[#DCCAB0]/40 text-[#433A32] transition-colors relative"
            title="Saved Bookmarks"
          >
            <Bookmark className="w-4 h-4" />
            {bookmarks.length > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#B96D50]"></span>
            )}
          </button>

          {/* Notification Bell */}
          <button
            onClick={onOpenNotifications}
            className="p-2 rounded-full hover:bg-[#DCCAB0]/40 text-[#433A32] transition-colors relative"
            title="Intelligence Alerts"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#B96D50] animate-pulse"></span>
          </button>

          {/* DEMO MODE Pill */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-full bg-[#DCCAB0]/35 border border-[#A86F45]/30 text-[11px] font-mono text-[#30251F]">
            <span className="w-2 h-2 rounded-full bg-[#B96D50]"></span>
            <span className="font-semibold tracking-wider">DEMO MODE</span>
          </div>

          {/* Round Avatar Profile / Settings Button */}
          <button
            onClick={onOpenSettings}
            className="w-8 h-8 rounded-full bg-[#30251F] text-[#F8F3E9] flex items-center justify-center hover:bg-[#B96D50] transition-colors"
            title="Profile & System Settings"
          >
            <User className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Global Search Modal */}
      {searchOpen && (
        <div className="fixed inset-0 z-50 bg-[#30251F]/40 backdrop-blur-sm flex items-start justify-center pt-24 animate-fade-in font-sans">
          <div className="bg-[#F8F3E9] w-full max-w-xl rounded-2xl shadow-2xl border border-[#DCCAB0] p-6 relative">
            <button
              onClick={() => setSearchOpen(false)}
              className="absolute top-4 right-4 p-1.5 rounded-full hover:bg-[#DCCAB0]/30 text-[#433A32]"
            >
              <X className="w-5 h-5" />
            </button>

            <form onSubmit={handleSearchSubmit} className="flex items-center space-x-3 border-b border-[#A86F45]/30 pb-3">
              <Search className="w-5 h-5 text-[#B96D50]" />
              <input
                type="text"
                autoFocus
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search person ID (P-0427), case ID (CASE-014), name, phone, or location..."
                className="w-full bg-transparent text-[#30251F] placeholder:text-[#433A32]/40 text-sm focus:outline-none"
              />
              <button
                type="submit"
                className="px-3 py-1 bg-[#B96D50] hover:bg-[#A86F45] text-white rounded-lg text-xs font-serif tracking-wider"
              >
                FIND
              </button>
            </form>

            <div className="mt-4">
              <span className="text-[10px] uppercase font-mono tracking-widest text-[#A86F45] block mb-2 font-semibold">
                Recent Searches
              </span>
              <div className="flex flex-wrap gap-2">
                {searchHistory.map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSearchQuery(item)}
                    className="px-2.5 py-1 rounded-md bg-[#DCCAB0]/30 hover:bg-[#DCCAB0]/60 text-xs text-[#30251F] border border-[#A86F45]/20 transition-colors"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bookmarks Drawer Overlay */}
      {bookmarksOpen && (
        <div className="fixed inset-0 z-50 bg-[#30251F]/40 backdrop-blur-sm flex justify-end font-sans">
          <div className="w-80 h-full bg-[#FAF6F0] border-l border-[#A86F45]/30 shadow-2xl p-6 flex flex-col justify-between animate-slide-left">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-[#DCCAB0]">
                <div className="flex items-center space-x-2">
                  <Bookmark className="w-4 h-4 text-[#B96D50]" />
                  <span className="font-serif font-bold text-sm text-[#30251F] tracking-wide">
                    BOOKMARKED ENTITIES
                  </span>
                </div>
                <button onClick={() => setBookmarksOpen(false)} className="p-1 rounded hover:bg-[#DCCAB0]/30 text-[#433A32]">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="mt-4 space-y-2">
                {bookmarks.length === 0 ? (
                  <p className="text-xs text-[#433A32]/60 py-6 text-center">No bookmarked entities yet.</p>
                ) : (
                  bookmarks.map((bId) => (
                    <div
                      key={bId}
                      className="p-3 rounded-lg border border-[#DCCAB0] bg-[#F8F3E9] hover:border-[#A86F45] transition-all flex items-center justify-between"
                    >
                      <div>
                        <span className="font-mono text-xs font-bold text-[#B96D50] block">{bId}</span>
                        <span className="text-[11px] text-[#433A32]">
                          {bId.startsWith('P-') ? 'Person of Interest' : 'Active Investigation Case'}
                        </span>
                      </div>
                      <button
                        onClick={() => {
                          setBookmarksOpen(false);
                          if (bId.startsWith('P-')) onNavigate('SUSPECT', bId);
                          else onNavigate('CASE', bId);
                        }}
                        className="px-2.5 py-1 text-[11px] font-mono bg-[#DCCAB0]/40 hover:bg-[#B96D50] hover:text-white rounded border border-[#A86F45]/20 transition-all font-semibold"
                      >
                        OPEN
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-[#DCCAB0] text-[11px] font-mono text-[#433A32]/60 text-center">
              Bookmarks stored locally
            </div>
          </div>
        </div>
      )}
    </>
  );
};
