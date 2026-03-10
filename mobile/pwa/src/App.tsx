import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';

const App = () => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    window.addEventListener('online', () => setIsOnline(true));
    window.addEventListener('offline', () => setIsOnline(false));
    return () => {
      window.removeEventListener('online', () => setIsOnline(true));
      window.removeEventListener('offline', () => setIsOnline(false));
    };
  }, []);

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100">
        <nav className="bg-blue-600 text-white p-4 flex justify-between">
          <div className="font-bold text-xl">RetailIQ PWA</div>
          <div className="flex gap-4">
            <Link to="/">Dashboard</Link>
            <Link to="/inventory">Inventory</Link>
            {!isOnline && <span className="bg-red-500 px-2 rounded">Offline Mode</span>}
          </div>
        </nav>
        
        <main className="p-4">
          <Routes>
            <Route path="/" element={<Dashboard isOnline={isOnline} />} />
            <Route path="/inventory" element={<Inventory isOnline={isOnline} />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};

const Dashboard = ({ isOnline }: { isOnline: boolean }) => (
  <div className="grid grid-cols-2 gap-4">
    <div className="bg-white p-4 rounded shadow">
      <h3 className="text-gray-500">Today's Sales</h3>
      <p className="text-2xl font-bold">₹45,230</p>
    </div>
    <div className="bg-white p-4 rounded shadow">
      <h3 className="text-gray-500">Transactions</h3>
      <p className="text-2xl font-bold">128</p>
    </div>
  </div>
);

const Inventory = ({ isOnline }: { isOnline: boolean }) => (
  <div className="bg-white p-4 rounded shadow">
    <h2 className="text-xl font-bold mb-4">Inventory List</h2>
    {isOnline ? (
      <ul>
        <li className="flex justify-between py-2 border-b">
          <span>Premium Coffee Beans</span>
          <span className="font-bold">₹350.00</span>
        </li>
      </ul>
    ) : (
      <div className="text-yellow-600">Showing cached inventory mode.</div>
    )}
  </div>
);

export default App;
