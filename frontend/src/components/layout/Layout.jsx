import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { RecordModal } from '../modals/RecordModal';
import { NewCaseModal } from '../modals/NewCaseModal';

export function Layout() {
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [newCaseModalOpen, setNewCaseModalOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 dark:bg-surface-dark text-slate-800 dark:text-slate-100">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header
          onOpenRecordModal={() => setRecordModalOpen(true)}
          onOpenNewCaseModal={() => setNewCaseModalOpen(true)}
        />
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto">
            <Outlet
              context={{
                openRecordModal: () => setRecordModalOpen(true),
                openNewCaseModal: () => setNewCaseModalOpen(true),
              }}
            />
          </div>
        </main>
      </div>

      <RecordModal
        isOpen={recordModalOpen}
        onClose={() => setRecordModalOpen(false)}
      />

      <NewCaseModal
        isOpen={newCaseModalOpen}
        onClose={() => setNewCaseModalOpen(false)}
      />
    </div>
  );
}
