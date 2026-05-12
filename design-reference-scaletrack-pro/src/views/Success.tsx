import { motion } from 'motion/react';
import { 
  CheckCircle2, Printer, RefreshCw, List, 
  FileText, History, MapPin, Clock, Globe
} from 'lucide-react';
import Layout from '../components/Layout';

interface SuccessProps {
  onNextOrder: () => void;
  onReturnToList: () => void;
}

export default function SuccessView({ onNextOrder, onReturnToList }: SuccessProps) {
  return (
    <Layout activeView="success">
      <div className="max-w-5xl mx-auto flex flex-col gap-8 h-full py-4">
        {/* Main Content Area */}
        <div className="grid grid-cols-12 gap-8 items-stretch flex-1">
          {/* Summary Card */}
          <div className="col-span-8 bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant overflow-hidden flex flex-col">
            <div className="p-12 text-center flex flex-col items-center">
              <motion.div 
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", damping: 12 }}
                className="w-28 h-28 bg-primary/10 text-primary rounded-full flex items-center justify-center mb-8"
              >
                <CheckCircle2 size={72} strokeWidth={2.5} />
              </motion.div>
              <h1 className="font-headline text-4xl font-extrabold text-on-surface mb-2 tracking-tight">Transaction Complete</h1>
              <p className="text-lg font-medium text-on-surface-variant">Order #ORD-2024-8842 has been verified successfully.</p>
            </div>

            <div className="px-12 pb-12">
              <div className="grid grid-cols-3 gap-8 border-y border-outline-variant py-8">
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-on-surface-variant mb-2 uppercase tracking-[0.2em]">Total SKUs</span>
                  <span className="text-3xl font-bold tabular-nums">12</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-on-surface-variant mb-2 uppercase tracking-[0.2em]">Total Weight</span>
                  <span className="text-3xl font-bold tabular-nums">1,500 <small className="text-sm opacity-60">kg</small></span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-on-surface-variant mb-2 uppercase tracking-[0.2em]">Variance</span>
                  <span className="text-3xl font-bold tabular-nums text-error">-2 <small className="text-sm opacity-60">kg</small></span>
                </div>
              </div>

              {/* Notification Box */}
              <div className="mt-8 bg-surface-container flex items-start gap-4 p-5 rounded-2xl border border-outline-variant/50">
                <FileText className="text-primary shrink-0 mt-1" size={24} />
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-bold text-on-surface leading-none uppercase tracking-wide">Auto-generated claim report</span>
                  <p className="text-sm font-medium text-on-surface-variant leading-relaxed">
                    A discrepancy of 2kg was detected. Claim #CLM-12345-A has been filed with Logistics Station Alpha-4 automatically.
                  </p>
                </div>
              </div>
            </div>

            {/* Warehouse Visual Component */}
            <div className="flex-1 min-h-[160px] relative mt-auto border-t border-outline-variant">
              <div className="absolute inset-0 warehouse-overlay opacity-40 mix-blend-multiply" />
              <div className="absolute inset-0 bg-gradient-to-t from-surface-container-lowest to-transparent" />
            </div>
          </div>

          {/* Action Sidebar */}
          <div className="col-span-4 flex flex-col gap-6">
            <div className="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant p-8 flex flex-col gap-4">
              <h3 className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.2em] mb-2">Next Steps</h3>
              
              <button className="w-full h-16 bg-primary text-on-primary rounded-xl font-bold flex items-center justify-center gap-3 hover:bg-primary-container transition-all active:scale-[0.98] shadow-lg shadow-primary/20 group">
                <Printer size={24} />
                <span>Print Labels (12)</span>
              </button>
              
              <button 
                onClick={onNextOrder}
                className="w-full h-16 border border-outline-variant text-on-surface rounded-xl font-bold flex items-center justify-center gap-3 hover:bg-surface-container-high transition-all active:scale-[0.98] group"
              >
                <RefreshCw size={24} className="group-hover:rotate-90 transition-transform" />
                <span>Process Next Order</span>
              </button>
              
              <button 
                onClick={onReturnToList}
                className="w-full h-16 border border-outline-variant text-on-surface rounded-xl font-bold flex items-center justify-center gap-3 hover:bg-surface-container-high transition-all active:scale-[0.98] group"
              >
                <List size={24} />
                <span>Return to Task List</span>
              </button>
            </div>

            {/* Meta Details */}
            <div className="bg-surface-container-high rounded-2xl p-8 flex flex-col gap-4 border border-outline-variant/30">
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Station</span>
                <div className="flex items-center gap-2 font-bold text-on-surface">
                  <MapPin size={14} className="text-primary" />
                  Alpha-4
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Timestamp</span>
                <div className="flex items-center gap-2 font-bold text-on-surface tabular-nums">
                  <Clock size={14} className="text-primary" />
                  14:02:45 UTC
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Gateway</span>
                <div className="flex items-center gap-2 font-bold text-on-surface">
                  <Globe size={14} className="text-primary" />
                  G-12_North
                </div>
              </div>
            </div>

            <button className="mt-auto flex items-center gap-2 text-[10px] font-bold text-primary hover:underline self-end uppercase tracking-[0.2em] px-2 py-1">
              <History size={14} />
              View Transaction Audit Log
            </button>
          </div>
        </div>
      </div>
    </Layout>
  );
}
