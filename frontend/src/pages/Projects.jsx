import React, { useState } from 'react';
import {
  FolderKanban,
  Plus,
  Layers,
  Trash2,
  Edit3,
  Check,
  Loader2,
  AlertTriangle,
  X,
  FileCode2,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';
import { api } from '../services/api';

export function Projects() {
  const { projects, currentProject, setCurrentProject, refreshProjects } = useProject();
  const { showToast } = useToast();

  const [isCreating, setIsCreating] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setLoading(true);
      await api.createProject({ name: name.trim(), description: description.trim() });
      await refreshProjects();
      showToast('Project created successfully!', 'success');
      setName('');
      setDescription('');
      setIsCreating(false);
    } catch (err) {
      showToast(err.message || 'Failed to create project', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editingProject || !editingProject.name.trim()) return;
    try {
      setLoading(true);
      await api.updateProject(editingProject.id, {
        name: editingProject.name.trim(),
        description: editingProject.description?.trim() || '',
      });
      await refreshProjects();
      showToast('Project updated successfully!', 'success');
      setEditingProject(null);
    } catch (err) {
      showToast(err.message || 'Failed to update project', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (proj, force = false) => {
    if (proj.id === 'default_project') {
      showToast('Default project workspace cannot be deleted.', 'error');
      return;
    }
    try {
      await api.deleteProject(proj.id, force);
      await refreshProjects();
      showToast('Project deleted successfully.', 'success');
      setDeleteConfirmation(null);
    } catch (err) {
      if (err.message && err.message.includes('force=true')) {
        // Show force confirmation dialog
        setDeleteConfirmation({
          project: proj,
          message: err.message,
        });
      } else {
        showToast(err.message || 'Failed to delete project', 'error');
      }
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Projects & Workspaces
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Organize test cases, executions, and environments across isolated projects.
          </p>
        </div>
        <button
          onClick={() => {
            setIsCreating(!isCreating);
            setEditingProject(null);
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Project</span>
        </button>
      </div>

      {/* Project Creation Form */}
      {isCreating && (
        <form
          onSubmit={handleCreate}
          className="p-5 rounded-2xl border border-brand-500/30 bg-brand-50/20 dark:bg-brand-950/20 space-y-4"
        >
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            Create New Workspace
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              type="text"
              placeholder="Project Name (e.g. Checkout Service)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              autoFocus
            />
            <input
              type="text"
              placeholder="Description (Optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsCreating(false)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Save Workspace'}
            </button>
          </div>
        </form>
      )}

      {/* Project Edit Modal */}
      {editingProject && (
        <form
          onSubmit={handleEditSubmit}
          className="p-5 rounded-2xl border border-indigo-500/30 bg-indigo-50/20 dark:bg-indigo-950/20 space-y-4"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Edit Workspace: {editingProject.id}
            </h3>
            <button
              type="button"
              onClick={() => setEditingProject(null)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              type="text"
              value={editingProject.name}
              onChange={(e) =>
                setEditingProject({ ...editingProject, name: e.target.value })
              }
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              autoFocus
            />
            <input
              type="text"
              value={editingProject.description || ''}
              onChange={(e) =>
                setEditingProject({ ...editingProject, description: e.target.value })
              }
              placeholder="Description"
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditingProject(null)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
            >
              {loading ? 'Saving...' : 'Update Workspace'}
            </button>
          </div>
        </form>
      )}

      {/* Delete Confirmation Warning Modal */}
      {deleteConfirmation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-surface-cardDark rounded-2xl border border-rose-200 dark:border-rose-900/50 shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="p-2 rounded-xl bg-rose-50 dark:bg-rose-950/60">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Delete Workspace Confirmation
              </h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {deleteConfirmation.message}
            </p>
            <p className="text-xs text-rose-500">
              Warning: Deleting this project will cascade and remove all associated test case metadata, suites, and execution logs.
            </p>
            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                onClick={() => setDeleteConfirmation(null)}
                className="px-4 py-2 text-xs font-semibold rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmation.project, true)}
                className="px-4 py-2 text-xs font-bold rounded-xl bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/20"
              >
                Confirm & Force Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Projects Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {projects.map((proj) => {
          const isActive = proj.id === currentProject?.id;
          return (
            <div
              key={proj.id}
              className={`p-5 rounded-2xl border transition-all flex flex-col justify-between ${
                isActive
                  ? 'border-brand-500 bg-brand-50/10 dark:bg-brand-950/20 shadow-md shadow-brand-500/10'
                  : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-slate-300 dark:hover:border-slate-700'
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      <FolderKanban className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-900 dark:text-white truncate">
                        {proj.name}
                      </h3>
                      {isActive && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-brand-600 dark:text-brand-400">
                          <Check className="w-3 h-3" /> Active Workspace
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setEditingProject(proj)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors"
                      title="Edit project"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    {proj.id !== 'default_project' && (
                      <button
                        onClick={() => handleDelete(proj, false)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                        title="Delete project"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>

                <p className="text-xs text-slate-500 mt-3 line-clamp-2">
                  {proj.description || 'No description provided.'}
                </p>
              </div>

              <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <FileCode2 className="w-3.5 h-3.5 text-slate-400" />
                    <strong className="text-slate-800 dark:text-slate-200">
                      {proj.testcase_count || 0}
                    </strong>
                  </span>
                  <span className="flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-slate-400" />
                    <strong className="text-slate-800 dark:text-slate-200">
                      {proj.suite_count || 0}
                    </strong>
                  </span>
                </div>

                {!isActive ? (
                  <button
                    onClick={() => {
                      setCurrentProject(proj);
                      showToast(`Switched active workspace to ${proj.name}`, 'info');
                    }}
                    className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-brand-600 hover:text-white dark:hover:bg-brand-600 transition-all text-slate-700 dark:text-slate-300"
                  >
                    Select
                  </button>
                ) : (
                  <span className="text-xs font-semibold text-emerald-500">Active</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
