import { ReactNode } from 'react';
import { Bluetooth, Wifi, Bell, AlertTriangle } from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
  operator?: string;
  showSidebar?: boolean;
  sidebarContent?: ReactNode;
  activeView?: string;
}

export default function Layout({ children, operator = "J. Doe", showSidebar, sidebarContent, activeView }: LayoutProps) {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface">
      {/* Top Bar */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-surface-container-lowest border-b border-outline-variant flex items-center justify-between px-6 z-50">
        <div className="flex items-center gap-4">
          <h1 className="font-headline text-2xl font-bold text-primary tracking-tight">ScaleTrack Pro</h1>
          {activeView && activeView !== 'login' && activeView !== 'dashboard' && (
            <div className="h-6 w-px bg-outline-variant mx-2 hidden md:block" />
          )}
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-4 text-primary">
            <Bluetooth size={20} />
            <Wifi size={20} />
            <div className="relative">
              <Bell size={20} className="text-on-surface-variant" />
              <div className="absolute -top-1 -right-1 w-2 h-2 bg-error rounded-full" />
            </div>
          </div>
          <div className="h-8 w-px bg-outline-variant" />
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs uppercase">
              {operator.split(' ').map(n => n[0]).join('')}
            </div>
            <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider hidden sm:block">
              Operator: {operator}
            </span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 pt-16 pb-10 overflow-hidden">
        {showSidebar && (
          <aside className="w-64 bg-surface-container-low border-r border-outline-variant p-4 flex flex-col gap-2 z-40">
            {sidebarContent}
          </aside>
        )}
        <main className={`flex-1 overflow-auto p-6 ${showSidebar ? '' : 'max-w-7xl mx-auto w-full'}`}>
          {children}
        </main>
      </div>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 h-10 bg-surface-container-high border-t border-outline-variant flex items-center justify-between px-6 z-50 text-[10px] font-bold tracking-widest uppercase text-on-surface-variant">
        <div className="flex items-center gap-8">
          <span>ScaleTrack v4.2.0 | System Stable</span>
          <div className="flex items-center gap-4">
            <button className="hover:text-primary transition-colors cursor-pointer">Sync Logs</button>
            <button className="hover:text-primary transition-colors cursor-pointer">Support</button>
          </div>
        </div>
        <button className="text-error flex items-center gap-2 hover:underline">
          <AlertTriangle size={14} fill="currentColor" className="text-error" />
          Emergency Stop
        </button>
      </footer>
    </div>
  );
}
