import { useState } from 'react';
import { motion } from 'motion/react';
import { Factory, Landmark, Badge, Lock, Eye, LogIn, CreditCard, ChevronRight } from 'lucide-react';

interface LoginProps {
  onLogin: () => void;
}

export default function LoginView({ onLogin }: LoginProps) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center p-6 architectural-bg overflow-hidden">
      {/* Visual Polish: Corner Accents */}
      <div className="absolute top-0 left-0 w-32 h-32 border-t-4 border-l-4 border-primary/10 m-8 rounded-tl-xl pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-32 h-32 border-b-4 border-r-4 border-primary/10 m-8 rounded-br-xl pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[480px] bg-surface-container-lowest rounded-2xl ambient-shadow border border-outline-variant p-10 flex flex-col gap-8 z-10"
      >
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 bg-primary-container rounded-2xl flex items-center justify-center mb-2">
            <Factory className="text-on-primary-container" size={36} />
          </div>
          <h1 className="font-headline text-3xl font-bold text-on-surface tracking-tight">ScaleTrack Pro</h1>
          <p className="text-sm text-on-surface-variant font-medium">Industrial Receiving Terminal v4.2.0</p>
        </div>

        <form 
          className="flex flex-col gap-6"
          onSubmit={(e) => { e.preventDefault(); onLogin(); }}
        >
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em] px-1">Enterprise ID</label>
            <div className="relative group">
              <Landmark className="absolute left-4 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors" size={20} />
              <input 
                type="text"
                placeholder="ENT-000-000"
                className="w-full h-14 pl-12 pr-4 bg-surface border border-outline-variant rounded-xl text-sm font-medium focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-outline-variant"
                required
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em] px-1">Staff ID</label>
            <div className="relative group">
              <Badge className="absolute left-4 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors" size={20} />
              <input 
                type="text"
                placeholder="ID-4829-X"
                className="w-full h-14 pl-12 pr-4 bg-surface border border-outline-variant rounded-xl text-sm font-medium focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-outline-variant"
                required
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center px-1">
              <label className="text-[10px] font-bold text-on-surface-variant uppercase tracking-[0.1em]">Password</label>
              <button type="button" className="text-[10px] font-bold text-primary hover:underline">Forgot?</button>
            </div>
            <div className="relative group">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors" size={20} />
              <input 
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                className="w-full h-14 pl-12 pr-12 bg-surface border border-outline-variant rounded-xl text-sm font-medium focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-outline-variant"
                required
              />
              <button 
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-outline hover:text-primary transition-colors"
              >
                {showPassword ? <Eye size={20} /> : <Eye size={20} className="opacity-50" />}
              </button>
            </div>
          </div>

          <button 
            type="submit"
            className="w-full h-14 bg-primary text-on-primary rounded-xl font-headline font-bold flex items-center justify-center gap-2 hover:bg-primary-container active:scale-[0.98] transition-all shadow-sm group"
          >
            Sign In
            <ChevronRight size={20} className="group-hover:translate-x-1 transition-transform" />
          </button>
        </form>

        <div className="flex items-center gap-4">
          <div className="h-px flex-1 bg-outline-variant" />
          <span className="text-[10px] font-bold text-outline uppercase tracking-[0.2em]">or</span>
          <div className="h-px flex-1 bg-outline-variant" />
        </div>

        <div className="flex flex-col gap-4">
          <button 
            onClick={onLogin}
            type="button"
            className="w-full h-14 border-2 border-primary text-primary rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-primary/5 active:scale-[0.98] transition-all"
          >
            <CreditCard size={20} />
            Scan ID Card
          </button>
          <p className="text-center text-xs font-bold text-on-surface-variant uppercase tracking-wider">
            Terminal Status: <span className="text-primary">Online</span>
          </p>
        </div>
      </motion.div>

      <footer className="mt-8 flex justify-between items-center w-full max-w-[480px] px-2 text-[10px] font-bold text-outline uppercase tracking-widest">
        <div className="flex flex-col">
          <span>Station Alpha-4</span>
          <span className="text-outline-variant">System Stable</span>
        </div>
        <div className="flex gap-6">
          <button className="hover:text-primary transition-colors">Support</button>
          <button className="text-error hover:underline transition-colors">Emergency Stop</button>
        </div>
      </footer>
    </div>
  );
}
