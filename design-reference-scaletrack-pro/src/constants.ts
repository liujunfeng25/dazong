import { Order, Device } from './types';

export const MOCK_ORDERS: Order[] = [
  {
    id: '#ORD-2024-8842',
    vendor: 'Global Logistics Corp',
    dock: 'Gate Alpha-4',
    status: 'in-progress',
    priority: 'urgent',
    receivedTime: '08:45 AM',
    items: [
      { id: '1', sku: 'ST-STEEL-440C', spec: 'Cold Rolled Sheet 2mm', expected: 250.00, actual: 250.45, unit: 'kg' },
      { id: '2', sku: 'ST-ALUM-6061', spec: 'Square Bar 50x50', expected: 120.00, unit: 'kg' },
      { id: '3', sku: 'ST-BRASS-C360', spec: 'Hexagon Rod 1/2"', expected: 45.50, unit: 'kg' },
    ]
  },
  {
    id: '#ORD-9430-B',
    vendor: 'Midwest Supply Co.',
    dock: 'Gate Beta-1',
    status: 'pending',
    priority: 'normal',
    receivedTime: '09:12 AM',
    items: []
  },
  {
    id: '#ORD-9435-F',
    vendor: 'Apex Industrial',
    dock: 'Gate G-12',
    status: 'pending',
    priority: 'normal',
    receivedTime: '10:05 AM',
    items: []
  }
];

export const MOCK_DEVICES: Device[] = [
  {
    id: 'scale-1',
    name: 'Scale model A-500',
    serialNumber: '992-PX-1029',
    distance: '0.5m',
    connected: true,
    battery: 94,
    lastCalibrated: 'Oct 24, 2023'
  },
  {
    id: 'scale-2',
    name: 'ScaleTrack B-200',
    serialNumber: '441-TR-8812',
    distance: '4.2m',
    connected: false
  },
  {
    id: 'scale-3',
    name: 'Alpha Platform V4',
    serialNumber: '109-KL-5521',
    distance: '7.8m',
    connected: false
  }
];
