import { motion } from 'motion/react';
import { 
  RefreshCw, Plus, Search, Calendar, 
  Building2, Filter, ChevronRight, AlertCircle,
  RotateCw, List, Settings
} from 'lucide-react';
import Layout from '../components/Layout';
import { MOCK_ORDERS } from '../constants';
import { Order } from '../types';

interface DashboardProps {
  onSelectOrder: (order: Order) => void;
  onNavigate: (view: any) => void;
}

export default function Dashboard({ onSelectOrder, onNavigate }: DashboardProps) {
  return (
    <Layout 
      activeView="dashboard"
      showSidebar
      sidebarContent={
        <div className="flex flex-col gap-1">
          <div className="mb-6 px-4 py-2">
            <h2 className="font-headline text-lg font-bold text-on-surface leading-tight text-balance">Receiving Terminal</h2>
            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest mt-1">Station Alpha-4</p>
          </div>
          
          <button className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-secondary-container text-on-secondary-container font-bold text-xs uppercase tracking-wider transition-all">
            <List size={18} />
            Task List
          </button>
          
          <button 
            onClick={() => onNavigate('device-management')}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-on-surface-variant hover:bg-surface-container-high font-bold text-xs uppercase tracking-wider transition-all"
          >
            <Settings size={18} />
            Device Management
          </button>
        </div>
      }
    >
      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {/* Header & Filter Bar */}
        <section className="bg-surface-container-lowest rounded-2xl border border-outline-variant p-6 shadow-sm flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <h1 className="font-headline text-3xl font-bold text-on-surface tracking-tight">Receiving Orders</h1>
            <div className="flex gap-3">
              <button className="flex items-center gap-2 px-6 h-12 bg-white border border-outline text-on-surface rounded-xl hover:bg-surface-container-low transition-colors font-bold text-xs uppercase tracking-wider">
                <RefreshCw size={16} />
                Refresh
              </button>
              <button className="flex items-center gap-2 px-6 h-12 bg-primary text-on-primary rounded-xl shadow-sm hover:opacity-90 transition-opacity font-bold text-xs uppercase tracking-wider">
                <Plus size={18} />
                New Manual Entry
              </button>
            </div>
          </div>

          <div className="grid grid-cols-12 gap-4 items-end">
            <div className="col-span-12 md:col-span-5 flex flex-col gap-1.5">
              <label className="text-[10px] font-bold text-on-surface-variant px-1 uppercase tracking-widest">Search Order / ID</label>
              <div className="relative group">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors" size={20} />
                <input 
                  type="text"
                  placeholder="Scan barcode or type ID..."
                  className="w-full h-14 pl-12 pr-4 bg-surface-container-low border border-outline-variant rounded-xl text-sm font-medium focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all outline-none"
                />
              </div>
            </div>
            <div className="col-span-12 sm:col-span-4 md:col-span-2 flex flex-col gap-1.5">
              <label className="text-[10px] font-bold text-on-surface-variant px-1 uppercase tracking-widest">By Date</label>
              <div className="relative">
                <Calendar className="absolute left-4 top-1/2 -translate-y-1/2 text-outline pointer-events-none" size={18} />
                <select className="w-full h-14 pl-11 pr-8 bg-surface-container-low border border-outline-variant rounded-xl text-sm font-bold uppercase tracking-wider appearance-none outline-none focus:border-primary transition-all">
                  <option>Today</option>
                  <option>Last 3 Days</option>
                  <option>This Week</option>
                </select>
              </div>
            </div>
            <div className="col-span-12 sm:col-span-4 md:col-span-3 flex flex-col gap-1.5">
              <label className="text-[10px] font-bold text-on-surface-variant px-1 uppercase tracking-widest">Vendor</label>
              <div className="relative">
                <Building2 className="absolute left-4 top-1/2 -translate-y-1/2 text-outline pointer-events-none" size={18} />
                <select className="w-full h-14 pl-11 pr-8 bg-surface-container-low border border-outline-variant rounded-xl text-sm font-medium appearance-none outline-none focus:border-primary transition-all">
                  <option>All Vendors</option>
                  <option>Global Logistics Corp</option>
                  <option>Midwest Supply Co.</option>
                  <option>Apex Industrial</option>
                </select>
              </div>
            </div>
            <div className="col-span-12 sm:col-span-4 md:col-span-2 flex flex-col gap-1.5">
              <label className="text-[10px] font-bold text-on-surface-variant px-1 uppercase tracking-widest">Status</label>
              <div className="relative">
                <Filter className="absolute left-4 top-1/2 -translate-y-1/2 text-outline pointer-events-none" size={18} />
                <select className="w-full h-14 pl-11 pr-8 bg-surface-container-low border border-outline-variant rounded-xl text-sm font-medium appearance-none outline-none focus:border-primary transition-all">
                  <option>All Statuses</option>
                  <option>Pending</option>
                  <option>In Progress</option>
                </select>
              </div>
            </div>
          </div>
        </section>

        {/* Orders List */}
        <section className="bg-surface-container-lowest rounded-2xl border border-outline-variant shadow-sm overflow-hidden flex flex-col">
          <div className="grid grid-cols-12 bg-surface-container-low border-b border-outline-variant px-6 py-4">
            <div className="col-span-3 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em]">Order ID</div>
            <div className="col-span-4 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em]">Vendor Name</div>
            <div className="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em] text-center">SKU Count</div>
            <div className="col-span-2 text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em]">Status</div>
            <div className="col-span-1" />
          </div>

          <div className="flex flex-col">
            {MOCK_ORDERS.map((order) => (
              <motion.div 
                key={order.id}
                whileHover={{ backgroundColor: 'var(--color-surface-container-lowest)' }}
                onClick={() => onSelectOrder(order)}
                className="grid grid-cols-12 px-6 py-5 items-center border-b border-outline-variant last:border-0 hover:bg-surface-container/30 transition-colors cursor-pointer group"
              >
                <div className="col-span-3">
                  <span className="font-bold text-primary tabular-nums">{order.id}</span>
                  <div className="text-[9px] font-bold text-outline-variant uppercase tracking-widest mt-0.5">Received: {order.receivedTime}</div>
                </div>
                <div className="col-span-4 font-bold text-on-surface">
                  {order.vendor}
                </div>
                <div className="col-span-2 text-center font-bold tabular-nums">
                  {order.items.length || 0}
                </div>
                <div className="col-span-2">
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 w-fit ${
                    order.status === 'in-progress' 
                      ? 'bg-secondary-container text-on-secondary-container' 
                      : 'bg-surface-container-high text-on-surface-variant'
                  }`}>
                    {order.status === 'in-progress' && <RotateCw size={10} className="animate-spin" />}
                    {order.status}
                  </span>
                </div>
                <div className="col-span-1 flex justify-end">
                  <div className="p-2 rounded-full group-hover:bg-primary/10 text-primary transition-all">
                    <ChevronRight size={20} />
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </div>
    </Layout>
  );
}
