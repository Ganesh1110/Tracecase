import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../services/api';

const ProjectContext = createContext({
  projects: [],
  currentProject: null,
  setCurrentProject: () => {},
  refreshProjects: async () => {},
  loading: true,
});

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
      if (data.length > 0) {
        const savedId = localStorage.getItem('qa_auto_active_project');
        const matched = data.find((p) => p.id === savedId);
        if (matched) {
          setCurrentProject(matched);
        } else {
          setCurrentProject(data[0]);
          localStorage.setItem('qa_auto_active_project', data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshProjects();
  }, []);

  const handleSetCurrentProject = (project) => {
    setCurrentProject(project);
    if (project?.id) {
      localStorage.setItem('qa_auto_active_project', project.id);
    }
  };

  return (
    <ProjectContext.Provider
      value={{
        projects,
        currentProject,
        setCurrentProject: handleSetCurrentProject,
        refreshProjects,
        loading,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export const useProject = () => useContext(ProjectContext);
