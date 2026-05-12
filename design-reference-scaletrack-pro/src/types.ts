export type View = 'login' | 'dashboard' | 'terminal' | 'success' | 'device-management';

export interface OrderItem {
  id: string;
  sku: string;
  spec: string;
  expected: number;
  actual?: number;
  unit: string;
}

export interface Order {
  id: string;
  vendor: string;
  dock: string;
  status: 'pending' | 'in-progress' | 'completed';
  priority: 'normal' | 'urgent';
  receivedTime: string;
  items: OrderItem[];
}

export interface Device {
  id: string;
  name: string;
  serialNumber: string;
  distance: string;
  connected?: boolean;
  battery?: number;
  lastCalibrated?: string;
}
