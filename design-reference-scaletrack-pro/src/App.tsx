/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import LoginView from './views/Login';
import Dashboard from './views/Dashboard';
import ScaleTerminal from './views/ScaleTerminal';
import SuccessView from './views/Success';
import DeviceManagement from './views/DeviceManagement';
import { View, Order } from './types';

export default function App() {
  const [currentView, setCurrentView] = useState<View>('login');
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

  const handleLogin = () => setCurrentView('dashboard');
  
  const handleSelectOrder = (order: Order) => {
    setSelectedOrder(order);
    setCurrentView('terminal');
  };

  const handleCompleteTransaction = () => {
    setCurrentView('success');
  };

  const handleReturnToDashboard = () => {
    setSelectedOrder(null);
    setCurrentView('dashboard');
  };

  const handleNavigate = (view: View) => setCurrentView(view);

  return (
    <div className="min-h-screen bg-surface select-none">
      <AnimatePresence mode="wait">
        {currentView === 'login' && (
          <motion.div
            key="login"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="w-full h-full"
          >
            <LoginView onLogin={handleLogin} />
          </motion.div>
        )}

        {currentView === 'dashboard' && (
          <motion.div
            key="dashboard"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.02 }}
            className="w-full h-full"
          >
            <Dashboard 
              onSelectOrder={handleSelectOrder} 
              onNavigate={handleNavigate}
            />
          </motion.div>
        )}

        {currentView === 'terminal' && selectedOrder && (
          <motion.div
            key="terminal"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="w-full h-full"
          >
            <ScaleTerminal 
              order={selectedOrder} 
              onBack={handleReturnToDashboard}
              onComplete={handleCompleteTransaction}
            />
          </motion.div>
        )}

        {currentView === 'success' && (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full h-full"
          >
            <SuccessView 
              onNextOrder={handleReturnToDashboard}
              onReturnToList={handleReturnToDashboard}
            />
          </motion.div>
        )}

        {currentView === 'device-management' && (
          <motion.div
            key="device-management"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="w-full h-full"
          >
            <DeviceManagement onBack={handleReturnToDashboard} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
