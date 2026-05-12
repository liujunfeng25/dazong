import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  ArrowLeft, CheckCircle2, Bluetooth, AlertTriangle, 
  RotateCcw, Save, ChevronRight, Info
} from 'lucide-react';
import Layout from '../components/Layout';
import { Order, OrderItem } from '../types';

interface ScaleTerminalProps {
  order: Order;
  onBack: () => void;
  onComplete: () => void;
}

export default function ScaleTerminal({ order, onBack, onComplete }: ScaleTerminalProps) {
  const [selectedItem, setSelectedItem] = useState<OrderItem | null>(order.items[0] || null);
  const [weight, setWeight] = useState(0);
  const [isStable, setIsStable] = useState(false);
  const [showOverride, setShowOverride] = useState(false);

  // Simulate real-time weight
  useEffect(() => {
    if (!selectedItem) return;
    
    setWeight(0);
    setIsStable(false);
    
    const target = selectedItem.actual || selectedItem.expected;
    const interval = setInterval(() => {
      setWeight(prev => {
        const diff = target - prev;
        if (Math.abs(diff) < 0.05) {
          setIsStable(true);
          return target;
        }
        return prev + diff * 0.1;
      });
    }, 50);

    return () => clearInterval(interval);
  }, [selectedItem]);

  const variance = selectedItem ? weight - selectedItem.expected : 0;
  const isAlert = Math.abs(variance) > (selectedItem?.expected || 0) * 0.001; // 0.1% threshold

  return (
    <Layout 
      activeView="terminal"
    >
      <div className="flex flex-col h-full gap-6">
        {/* Navigation Shell */}
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack}
            className="flex items-center gap-2 p-2 px-3 rounded-lg hover:bg-surface-container-high transition-colors font-bold text-xs uppercase tracking-wider text-on-surface-variant group"
          >
            <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
            Task List
          </button>
          <div className="h-6 w-px bg-outline-variant" />
          <h2 className="font-headline text-xl font-bold text-primary">Terminal Interface</h2>
        </div>

        <main className="flex-1 flex gap-6 overflow-hidden">
          {/* Left Column: Order & Item List */}
          <section className="w-[40%] flex flex-col gap-6 overflow-hidden">
            <div className="bg-surface-container-lowest rounded-2xl p-6 ambient-shadow border border-outline-variant">
              <div className="flex justify-between items-start mb-6">
                <div>
                  <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.2em] mb-1">Active Order</p>
                  <h3 className="font-headline text-2xl font-bold text-on-surface">{order.id}</h3>
                </div>
                <span className="bg-secondary-container text-on-secondary-container px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider">
                  In Progress
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Supplier</span>
                  <span className="text-sm font-bold text-on-surface">{order.vendor}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Dock</span>
                  <span className="text-sm font-bold text-on-surface">{order.dock}</span>
                </div>
              </div>
            </div>

            <div className="flex-1 bg-surface-container-lowest rounded-2xl overflow-hidden ambient-shadow border border-outline-variant flex flex-col">
              <div className="bg-surface-container-low px-6 py-4 border-b border-outline-variant">
                <h4 className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.2em]">Receiving Item List</h4>
              </div>
              <div className="flex-1 overflow-y-auto">
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-2 px-6 py-2 bg-surface-container-low/50 border-b border-outline-variant">
                  <div className="col-span-5 text-[9px] font-bold text-on-surface-variant uppercase tracking-wider">SKU / SPEC</div>
                  <div className="col-span-3 text-[9px] font-bold text-on-surface-variant uppercase tracking-wider text-right">Expected</div>
                  <div className="col-span-4 text-[9px] font-bold text-on-surface-variant uppercase tracking-wider text-right">Actual</div>
                </div>
                {/* Items */}
                {order.items.map((item) => (
                  <motion.div 
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    className={`grid grid-cols-12 gap-2 px-6 py-4 transition-all cursor-pointer border-l-4 ${
                      selectedItem?.id === item.id 
                        ? 'border-primary bg-primary/5' 
                        : 'border-transparent hover:bg-surface-container-low border-b border-outline-variant last:border-b-0'
                    }`}
                  >
                    <div className="col-span-5">
                      <p className="text-sm font-bold text-on-surface tabular-nums">{item.sku}</p>
                      <p className="text-[10px] font-medium text-on-surface-variant">{item.spec}</p>
                    </div>
                    <div className="col-span-3 text-right">
                      <span className="text-sm font-bold tabular-nums">{item.expected.toFixed(2)} {item.unit}</span>
                    </div>
                    <div className="col-span-4 text-right flex flex-col items-end">
                      <span className={`text-sm font-bold tabular-nums ${item.actual ? 'text-primary' : 'text-outline-variant'}`}>
                        {item.actual ? `${item.actual.toFixed(2)} ${item.unit}` : '--'}
                      </span>
                      {item.actual && (
                        <span className="text-[9px] font-extrabold text-error uppercase mt-0.5 whitespace-nowrap">
                          {Math.abs(item.actual - item.expected) > item.expected * 0.001 ? '+0.45 (ALERT)' : ''}
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          {/* Right Column: Real-time weight display */}
          <section className="w-[60%] flex flex-col gap-6">
            <div className="flex-1 bg-surface-container-lowest rounded-2xl p-10 ambient-shadow border-2 border-outline-variant flex flex-col items-center justify-center relative overflow-hidden">
              {/* Status Badges */}
              <div className="absolute top-6 left-6 flex items-center gap-4">
                <div className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-colors ${
                  isStable ? 'bg-primary/10 text-primary' : 'bg-surface-container-high text-on-surface-variant animate-pulse'
                }`}>
                  <CheckCircle2 size={20} fill={isStable ? "currentColor" : "none"} className={isStable ? "text-primary dark" : ""} />
                  <span className="text-[10px] font-bold uppercase tracking-widest">{isStable ? 'Stable Reading' : 'Settling Scale...'}</span>
                </div>
                <div className="bg-surface-container-low text-on-surface-variant px-4 py-2 rounded-xl flex items-center gap-2 border border-outline-variant/30">
                  <Bluetooth size={20} className="text-primary" />
                  <span className="text-[10px] font-bold uppercase tracking-widest">Scale: BR-909</span>
                </div>
              </div>
              <div className="absolute top-6 right-6">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Calibrated: 2024-05-12</span>
              </div>

              {/* Giant Weight */}
              <div className="flex flex-col items-center">
                <motion.span 
                  key={selectedItem?.id}
                  initial={{ scale: 0.95, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className="text-[160px] leading-none font-bold tabular-nums tracking-tighter text-on-surface"
                >
                  {weight.toFixed(2)}
                </motion.span>
                <span className="font-headline text-2xl font-bold text-on-surface-variant mt-2">KILOGRAMS (kg)</span>
              </div>

              {/* Alert Badge */}
              <AnimatePresence>
                {isAlert && isStable && (
                  <motion.div 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    className="mt-12 flex items-center gap-4 p-5 bg-error-container text-on-error-container rounded-2xl border border-error/20 max-w-lg shadow-lg"
                  >
                    <AlertTriangle size={36} />
                    <div className="flex-1">
                      <p className="text-xs font-black uppercase tracking-wider">Weight Alert: +{variance.toFixed(2)}kg Variance</p>
                      <p className="text-xs font-medium opacity-80 mt-1 leading-relaxed">Reading exceeds the standard 0.1% logic for this item class. Manual verification required.</p>
                    </div>
                    <button 
                      onClick={() => setShowOverride(true)}
                      className="ml-4 border-2 border-on-error-container/20 hover:bg-on-error-container/10 transition-colors px-4 py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-widest"
                    >
                      Confirm Manual Override
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Actions */}
            <div className="grid grid-cols-2 gap-6 h-28">
              <button className="bg-surface-container-high hover:bg-surface-container text-on-surface-variant flex items-center justify-center gap-4 rounded-2xl transition-all active:scale-[0.98] group">
                <RotateCcw size={32} className="group-hover:rotate-180 transition-transform duration-500" />
                <span className="font-headline text-2xl font-extrabold uppercase tracking-widest">Tare Scale</span>
              </button>
              <button 
                onClick={onComplete}
                disabled={!isStable}
                className="bg-primary hover:bg-primary-container text-on-primary rounded-2xl flex items-center justify-center gap-4 transition-all shadow-xl active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed group"
              >
                <Save size={32} className="group-hover:scale-110 transition-transform" />
                <span className="font-headline text-2xl font-extrabold uppercase tracking-widest">Lock & Confirm</span>
              </button>
            </div>
          </section>
        </main>
      </div>
    </Layout>
  );
}
