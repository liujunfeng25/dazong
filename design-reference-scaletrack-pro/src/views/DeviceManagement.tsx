import { 
  ArrowLeft, Search, Bluetooth, SignalHigh, 
  Battery, MonitorX, Lightbulb, Headphones,
  CheckCircle2, Loader2, Unlink
} from 'lucide-react';
import { motion } from 'motion/react';
import Layout from '../components/Layout';
import { MOCK_DEVICES } from '../constants';

interface DeviceManagementProps {
  onBack: () => void;
}

export default function DeviceManagement({ onBack }: DeviceManagementProps) {
  const connectedDevice = MOCK_DEVICES.find(d => d.connected);
  const otherDevices = MOCK_DEVICES.filter(d => !d.connected);

  return (
    <Layout activeView="device-management">
      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        <div className="flex justify-between items-center bg-surface-container-lowest p-6 rounded-2xl ambient-shadow border border-outline-variant">
          <div className="flex items-center gap-4">
            <button 
              onClick={onBack}
              className="p-2 hover:bg-surface-container rounded-lg transition-colors group"
            >
              <ArrowLeft size={24} className="group-hover:-translate-x-1 transition-transform" />
            </button>
            <div>
              <h1 className="font-headline text-3xl font-bold text-on-surface tracking-tight">Industrial Nodes</h1>
              <p className="text-sm font-bold text-on-surface-variant uppercase tracking-widest mt-1">Peripheral Management</p>
            </div>
          </div>
          <div className="flex items-center gap-4 px-6 py-3 rounded-2xl bg-secondary-container/20 text-secondary border border-secondary-container/30">
            <Bluetooth size={24} className="animate-pulse" />
            <div className="flex flex-col">
              <span className="text-[10px] font-black uppercase tracking-widest">Scanning Protocols</span>
              <span className="text-xs font-bold">Bluetooth v5.4 BLE Enabled</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-8">
          {/* Main List */}
          <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
            {/* Connected Section */}
            {connectedDevice && (
              <section className="bg-surface-container-lowest rounded-2xl ambient-shadow p-8 border border-outline-variant">
                <div className="flex justify-between items-start mb-8">
                  <div>
                    <span className="text-[10px] font-black text-primary uppercase tracking-[0.2em] block mb-2">Connected Transceiver</span>
                    <h3 className="font-headline text-2xl font-bold">{connectedDevice.name}</h3>
                    <p className="text-on-surface-variant font-bold text-xs tabular-nums mt-1 uppercase tracking-widest">S/N: {connectedDevice.serialNumber}</p>
                  </div>
                  <div className="flex items-center gap-10">
                    <div className="flex flex-col items-center">
                      <SignalHigh size={32} className="text-primary" />
                      <span className="text-[10px] font-bold uppercase tracking-widest mt-1">Stable</span>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="relative">
                        <Battery size={32} className="text-primary" />
                        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-on-surface pt-1">{connectedDevice.battery}%</span>
                      </div>
                      <span className="text-[10px] font-bold uppercase tracking-widest mt-1">Internal</span>
                    </div>
                  </div>
                </div>

                <div className="bg-surface-container/50 rounded-2xl p-6 flex items-center justify-between border border-outline-variant/30 mb-6">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 bg-white rounded-xl flex items-center justify-center border border-outline-variant">
                      <Search size={28} className="text-on-surface-variant" />
                    </div>
                    <div>
                      <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Software Calibrated</p>
                      <p className="font-bold text-sm tabular-nums">{connectedDevice.lastCalibrated}</p>
                    </div>
                  </div>
                  <button className="h-12 px-8 bg-white border border-outline text-on-surface rounded-xl font-bold text-xs uppercase tracking-widest hover:bg-surface-container transition-all flex items-center gap-2 group">
                    <Unlink size={16} className="group-hover:rotate-12 transition-transform" />
                    Disconnect Hardware
                  </button>
                </div>

                <div className="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-widest">
                  <CheckCircle2 size={16} fill="currentColor" />
                  Ultra-low latency active (4ms polling)
                </div>
              </section>
            )}

            {/* Nearby Devices */}
            <section className="bg-surface-container-lowest rounded-2xl ambient-shadow border border-outline-variant flex flex-col">
              <div className="p-8 border-b border-outline-variant flex justify-between items-center">
                <div>
                  <h3 className="font-headline text-2xl font-bold tracking-tight">Nearby Terminals</h3>
                  <p className="text-on-surface-variant text-sm font-medium mt-1">Auto-detected industrial nodes in 10m radius</p>
                </div>
                <div className="flex items-center gap-3">
                  <Loader2 size={20} className="text-primary animate-spin" />
                  <span className="text-[10px] font-black text-primary uppercase tracking-widest">Live Discovering</span>
                </div>
              </div>

              <div className="flex flex-col divide-y divide-outline-variant">
                {otherDevices.map((device) => (
                  <div key={device.id} className="p-8 flex items-center justify-between hover:bg-surface-container-low/50 transition-all cursor-default group">
                    <div className="flex items-center gap-6">
                      <div className="w-12 h-12 bg-surface-container-low rounded-xl flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                        <Bluetooth size={24} className="text-outline group-hover:text-primary transition-colors" />
                      </div>
                      <div>
                        <p className="font-bold text-on-surface text-lg">{device.name}</p>
                        <p className="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest tabular-nums mt-0.5">S/N: {device.serialNumber} • {device.distance} Away</p>
                      </div>
                    </div>
                    <button className="h-12 px-8 bg-primary text-on-primary rounded-xl font-bold text-xs uppercase tracking-widest hover:bg-primary-container transition-all active:scale-[0.98] shadow-sm">
                      Pair Remote Node
                    </button>
                  </div>
                ))}
              </div>
              <div className="p-4 bg-surface-container-low/30 text-center">
                <button className="text-[10px] font-black text-primary uppercase tracking-[0.2em] hover:underline">Diagnostic Node Map</button>
              </div>
            </section>
          </div>

          {/* Sidebar */}
          <aside className="col-span-12 lg:col-span-4 flex flex-col gap-6">
            <div className="bg-surface-container-high rounded-2xl p-8 border border-outline-variant flex flex-col gap-8">
              <div className="flex items-center gap-4">
                <Lightbulb size={24} className="text-primary" />
                <h4 className="font-headline text-lg font-bold text-on-surface tracking-tight">Expert Troubleshooting</h4>
              </div>
              
              <div className="flex flex-col gap-4">
                {[
                  { title: "EM Interference", body: "Avoid metallic clusters within 0.5m of the wireless transceiver point." },
                  { title: "Battery Cycles", body: "Nodes below 15% charge enter low-power state with reduced signal polling." },
                  { title: "Firmware Check", body: "v4.2.0 requires active protocol handshakes with Alpha gates." }
                ].map((tip, i) => (
                  <div key={i} className="p-5 bg-white rounded-xl border border-outline-variant/50 flex flex-col gap-1.5 shadow-sm">
                    <span className="text-[10px] font-black text-primary uppercase tracking-widest">{tip.title}</span>
                    <p className="text-sm font-medium text-on-surface-variant leading-relaxed">{tip.body}</p>
                  </div>
                ))}
              </div>

              <div className="pt-4 border-t border-outline-variant/30 flex flex-col gap-4 mt-2">
                <div className="w-full h-32 architectural-bg rounded-xl opacity-20 grayscale border border-outline-variant" />
                <button className="w-full flex items-center justify-center gap-3 font-bold text-primary hover:underline text-xs uppercase tracking-widest">
                  <Headphones size={18} />
                  Tier 2 Technical Support
                </button>
              </div>
            </div>

            <div className="bg-primary text-on-primary rounded-2xl p-8 ambient-shadow relative overflow-hidden">
              <div className="relative z-10">
                <h4 className="font-bold text-lg mb-2">Network Insights</h4>
                <p className="text-sm font-medium opacity-90 leading-relaxed mb-6 italic">"Real-time scale integration reduces manual terminal latency by up to 42% per shift."</p>
                <div className="flex items-center gap-4">
                  <div className="flex -space-x-3">
                    {[1,2,3].map(i => (
                      <div key={i} className="w-9 h-9 rounded-full border-2 border-primary bg-primary-container/50 flex items-center justify-center text-[10px] font-bold text-white shadow-sm ring-1 ring-white/10">EX</div>
                    ))}
                    <div className="w-9 h-9 rounded-full border-2 border-primary bg-on-primary-fixed-variant flex items-center justify-center text-[10px] font-bold text-white">+8</div>
                  </div>
                  <span className="text-[10px] font-black uppercase tracking-widest opacity-80">Logistics Lead Verified</span>
                </div>
              </div>
              <div className="absolute top-0 right-0 p-4 opacity-10">
                <Bluetooth size={120} strokeWidth={1} />
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Layout>
  );
}
