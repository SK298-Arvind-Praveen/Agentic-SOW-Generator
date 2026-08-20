import React, { useState, useCallback, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Wand2, User, Calendar, Upload, FileText, X, AlertCircle, Eye, Edit, ArrowLeft, Loader } from 'lucide-react';
import { toast } from 'react-toastify';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import apiService from '../services/apiService';
import SOWSectionChecklist, { availableSowSectionIds } from './SOWSectionChecklist';
import './SOWGenerator.css';

interface SOWGeneratorData {
  generationMode: 'poc' | 'production' | 'poc-to-production';
  companyName: string;
  authorOrganization: string;
  authorName: string;
  documentDate: string;
  projectObjective: string;
  uploadedFiles?: File[];
  selectedSowSections?: string[];
}

interface SOWGeneratorProps {
  selectedMode?: 'poc' | 'production' | 'poc-to-production';
  onGenerateSuccess?: (data: SOWGeneratorData) => void;
  onGenerateError?: (error: string) => void;
  // New props for project-based creation
  projectId?: string;
  projectName?: string;
  accountName?: string;
  accountId?: string;
  onSuccess?: () => void;
  onCancel?: () => void;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_FILE_TYPES = ['.pdf', '.doc', '.docx', '.txt'];
const MIN_OBJECTIVE_LENGTH = 20; // Reduced for easier testing

// Helper function to determine the best company name
const getCompanyName = (accountName?: string, projectName?: string, currentValue?: string): string => {
  if (accountName && accountName.trim()) return accountName.trim();
  if (projectName && projectName.trim() && (!currentValue || currentValue === 'Loading...' || currentValue === '')) return projectName.trim();
  if (currentValue && currentValue !== 'Loading...' && currentValue.trim()) return currentValue.trim();
  return '';
};

// Helper function to determine the best project name
const getProjectName = (projectName?: string, companyName?: string): string => {
  if (projectName && projectName.trim()) return projectName.trim();
  if (companyName && companyName !== 'Loading...' && companyName.trim()) return companyName.trim();
  return 'ShellKode';
};

const SOWGenerator: React.FC<SOWGeneratorProps> = ({
  selectedMode,
  onGenerateSuccess,
  onGenerateError,
  projectId,
  projectName,
  accountName,
  accountId,
  onSuccess,
  onCancel
}) => {
  const navigate = useNavigate();

  // If projectId is provided, use it for project-based SOW creation
  const isProjectBased = !!projectId;

  const [formData, setFormData] = useState<SOWGeneratorData>({
    generationMode: selectedMode || 'poc',
    companyName: accountName || '',
    authorOrganization: isProjectBased ? (projectName || '') : 'ShellKode',
    authorName: '',
    documentDate: new Date().toISOString().split('T')[0],
    projectObjective: '',
    uploadedFiles: []
  });
  const [selectedSowSections, setSelectedSowSections] = useState<string[]>(
    availableSowSectionIds(selectedMode || 'poc')
  );

  // Track if initial auto-population has been done
  const [initialPopulationDone, setInitialPopulationDone] = useState(false);

  // Update company name and project name when props change (only initially)
  useEffect(() => {
    console.log('SOWGenerator - accountName:', accountName);
    console.log('SOWGenerator - isProjectBased:', isProjectBased);
    console.log('SOWGenerator - projectName:', projectName);
    console.log('SOWGenerator - initialPopulationDone:', initialPopulationDone);

    if (isProjectBased && (accountName || projectName)) {
      const newCompanyName = getCompanyName(accountName, projectName, formData.companyName);
      const newProjectName = getProjectName(projectName, newCompanyName);
      
      let hasUpdates = false;
      const updates: Partial<SOWGeneratorData> = {};
      
      // Always update company name if we have a better value and current is empty or placeholder
      if (newCompanyName && (
        !formData.companyName || 
        formData.companyName === 'Loading...' || 
        formData.companyName === '' ||
        formData.companyName === 'Auto-populated from project context'
      )) {
        updates.companyName = newCompanyName;
        hasUpdates = true;
        console.log('🔄 Auto-populating company name:', newCompanyName);
      }
      
      // Only auto-populate project name initially, don't override user edits
      if (newProjectName && (
        !formData.authorOrganization || 
        formData.authorOrganization === 'Loading...' || 
        formData.authorOrganization === 'ShellKode' ||
        formData.authorOrganization === ''
      )) {
        updates.authorOrganization = newProjectName;
        hasUpdates = true;
        console.log('🔄 Auto-populating project name:', newProjectName);
      }
      
      if (hasUpdates) {
        console.log('📝 Applying auto-population updates:', updates);
        setFormData(prev => ({ ...prev, ...updates }));
        
        // Only show notification once when we have meaningful updates
        if (!initialPopulationDone) {
          setInitialPopulationDone(true);
          toast.info('📝 Form fields auto-populated from project context', {
            position: 'bottom-right',
            autoClose: 3000,
            hideProgressBar: true,
            closeOnClick: true,
            pauseOnHover: true,
          });
        }
      }
    }
  }, [accountName, isProjectBased, projectName, initialPopulationDone]);

  // Auto-populate company name when accountName becomes available
  useEffect(() => {
    console.log('🚀 SOWGenerator - Props changed:', { accountName, projectName, isProjectBased });
    
    if (isProjectBased && accountName && (!formData.companyName || formData.companyName === '')) {
      console.log('🔄 Auto-populating company name with:', accountName);
      setFormData(prev => ({
        ...prev,
        companyName: accountName
      }));
      
      toast.success('✅ Company name auto-populated from account', {
        position: 'bottom-right',
        autoClose: 2000,
      });
    }
    
    if (isProjectBased && projectName && (!formData.authorOrganization || formData.authorOrganization === '' || formData.authorOrganization === 'ShellKode')) {
      console.log('🔄 Auto-populating project name with:', projectName);
      setFormData(prev => ({
        ...prev,
        authorOrganization: projectName
      }));
    }
  }, [accountName, projectName, isProjectBased]);

  const [isGenerating, setIsGenerating] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewProgress, setPreviewProgress] = useState(0);
  const [targetProgress, setTargetProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const [fileUploadError, setFileUploadError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState<any>(null);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [sectionInputs, setSectionInputs] = useState<Record<string, string>>({});
  const [hasPreviewGenerated, setHasPreviewGenerated] = useState(false);
  const [isFullReplace, setIsFullReplace] = useState(false);
  const [availableSections, setAvailableSections] = useState<{key: string, name: string}[]>([]);

  // Auto-load preview from draft if coming from drafts modal
  useEffect(() => {
    const loadingFromDraft = localStorage.getItem('loadingFromDraft');
    const previewId = localStorage.getItem('lastPreviewId');

    if (loadingFromDraft === 'true' && previewId) {
      console.log('📝 Loading draft preview:', previewId);

      // Clear the flag
      localStorage.removeItem('loadingFromDraft');

      // Load the preview — if ready show modal, if still generating start polling
      const loadDraftPreview = async () => {
        try {
          const statusResponse = await apiService.checkPreviewStatus(previewId);
          console.log('Draft preview status response:', statusResponse);

          const isReady = statusResponse.success && (
            statusResponse.progress === 100 ||
            statusResponse.status === 'ready' ||
            statusResponse.status === 'completed'
          );

          if (isReady && (statusResponse.content || statusResponse.updated_content)) {
            console.log('✅ Draft preview loaded and ready:', statusResponse);
            setPreviewData(statusResponse);
            setShowPreviewModal(true);
            setHasPreviewGenerated(true);
            toast.success('Draft loaded! You can now edit or finalize.', {
              position: 'top-right',
              autoClose: 4000,
            });
          } else {
            // Preview still generating — start polling until ready
            const currentProgress = statusResponse.progress || 0;
            toast.info(`Generating preview... ${currentProgress}% complete`, {
              position: 'top-right',
              autoClose: 3000,
            });

            const pollInterval = setInterval(async () => {
              try {
                const pollResponse = await apiService.checkPreviewStatus(previewId);
                const done = pollResponse.success && (
                  pollResponse.progress === 100 ||
                  pollResponse.status === 'ready' ||
                  pollResponse.status === 'completed'
                );

                if (done && (pollResponse.content || pollResponse.updated_content)) {
                  clearInterval(pollInterval);
                  setPreviewData(pollResponse);
                  setShowPreviewModal(true);
                  setHasPreviewGenerated(true);
                  toast.success('Preview ready! Opening editor...', {
                    position: 'top-right',
                    autoClose: 3000,
                  });
                } else if (pollResponse.status === 'failed' || pollResponse.has_error) {
                  clearInterval(pollInterval);
                  toast.error(`Preview generation failed: ${pollResponse.error || 'Unknown error'}`, {
                    position: 'top-right',
                    autoClose: 6000,
                  });
                }
              } catch (err) {
                clearInterval(pollInterval);
                console.error('Draft poll error:', err);
              }
            }, 8000);

            // Safety: stop polling after 6 minutes
            setTimeout(() => clearInterval(pollInterval), 360000);
          }
        } catch (error) {
          console.error('Error loading draft:', error);
          toast.error('Failed to load draft preview', {
            position: 'top-right',
            autoClose: 3000,
          });
        }
      };

      loadDraftPreview();
    }
  }, []);
  const [modalData, setModalData] = useState({
    sowContent: `Table of Contents

About Shellkode                                                                                    3
About WaterTec                                                                                     3
Project Overview / Objectives                                                                      
Scope of Work                                                                                      3
Technical Specifications & System Design                                                           3
Architecture & Integrations                                                                        4
Testing & Acceptance Criteria                                                                      4
Customer Dependencies & Responsibilities                                                           4
Assumptions                                                                                        4
Out of Scope                                                                                       4
Timelines and Deliverables                                                                         4
Commercials & Duration of Work                                                                     4
Success Criteria                                                                                   5
Day-2 Operations & Support                                                                         5
Feature Extensions                                                                                 5
Data Ownership & IP Rights                                                                         5
Deliverable Acceptance                                                                             5
Change Management                                                                                  6
Project Plan Termination                                                                           6
Contacts and Reporting                                                                             6
Marketing Authorization                                                                            7
Terms & Conditions                                                                                 7
Acceptance and Signatories to Statement of Work                                                    8

About Shellkode
Shellkode specializes in developing advanced data and AI solutions for businesses. The company builds robust data foundations that transform raw inputs into actionable intelligence, creates self-improving machine learning systems, and offers AI-driven services to modernize applications and infrastructure for cloud environments. Shellkode's expertise lies in enhancing data processing, predictive modeling, and cloud migration capabilities.

About WaterTec
WaterTec delivers innovative water management solutions focused on optimizing efficiency and sustainability for commercial and industrial applications. Their comprehensive service portfolio includes advanced filtration systems, wastewater treatment technologies, and smart monitoring capabilities, all designed to help clients reduce operational costs while maintaining compliance with environmental regulations.

Project Overview / Objectives
Content not available

Scope of Work
Error: Content for Scope of Work missing.

Technical Specifications & System Design
Error: Content for Technical Specifications & System Design missing.

Architecture & Integrations
Error: Content for Architecture & Integrations missing.

Testing & Acceptance Criteria
Error: Content for Testing & Acceptance Criteria missing.

Customer Dependencies & Responsibilities
Error: Content for Customer Dependencies & Responsibilities missing.

Assumptions
Error: Content for Assumptions missing.

Out of Scope
Error: Content for Out of Scope missing.

Timelines and Deliverables
Error: Content for Timelines and Deliverables missing.

Commercials & Duration of Work
Error: Content for Commercials & Duration of Work missing.

Success Criteria
Error: Content for Success Criteria missing.

Day-2 Operations & Support
Error: Content for Day-2 Operations & Support missing.

Feature Extensions
Error: Content for Feature Extensions missing.

Data Ownership & IP Rights
• Customer retains ownership of all data and outputs
• ShellKode retains rights to generic frameworks and accelerators
• No customer data used for training outside customer AWS account

Deliverable Acceptance
Customers will notify Shellkode in writing within ten (10) calendar days of receiving a Deliverable whether it accepts or rejects that Deliverable. If no notification is delivered to ShellKode within this period, the Deliverable will be considered accepted. As a time and materials engagement, changes to a rejected Deliverable constitute billable project time unless the parties determine that such Deliverable was not performed in accordance with good commercial practices.

Change Management
Changes to project scope, incorrect assumptions, or missing prerequisites may affect cost, resources, or scheduling. Other circumstances may arise beyond Shellkode's control that may cause it to be unable to accomplish the project objectives and would require a modification to this proposal. Any such modification shall be memorialized in a mutually executed change order that details material changes to staff requirements, deliverables, fees, and milestones, as applicable. If the parties do not agree to such a proposed change order, then either may suspend the Services to allow time for the parties to agree on an alternative change order. Should Services be suspended for a consecutive period of five (5) business days, either party may thereafter terminate this proposal immediately upon notice.

Project Plan Termination
Upon termination of this Project Plan executed in accordance with the terms of the Agreement, Customer shall pay Shellkode for any Customer-approved Services performed and expenses incurred up to the date of the termination and any expenses necessarily and reasonably incurred by AWS Partner in terminating Customer-approved obligations to third parties.

Contacts and Reporting
Name                Title                      Email                           Phone
Bala                Delivery Head              bala@shellkode.com              +91 9538916855
Bakrudeen K         AI/ML Head                 bakrudeen.k@shellkode.com       +91 7845406910
Suman Perumal       Solution Architect         suman.p@shellkode.com           +91 9738241191
Velmurugan S        Delivery Manager           vel@shellkode.com               +91 9994607336

Marketing Authorization
Upon successful completion of the project, Customer agrees to provide a reference for Shellkode for services provided under this SOW. Shellkode agrees to follow the Customer's terms and conditions for the use of such reference and the Customer's name and logo.

Terms & Conditions
• Working hours
  ● Standard work hours are 10 am - 07 pm IST Monday to Friday.
  ● If the resource has to be summoned before or after the specified business hour prior notice is to be issued.
  ● However, the above statement is not applicable during the production release cycle/P1 issues.
• The SLAs of Cloud services are governed and owned by Cloud Platform directly.
• The effort estimate is limited to the understood scope of work. Any substantial change in the scope may lead to the enhancement in the commercials and effort.
• Changes to the scope of the services shall be mutually agreed to in writing between Customer and Shellkode. Changes to project scope, assumptions, etc. may have cost, resource, or timeline implications.
• The client may terminate this agreement or ramp down resources with or without cause upon thirty (30) days written notice to Shellkode.
• The client will provide feedback on the deliverables submitted by the Shellkode team at the earliest During the above-mentioned period, Shellkode resources will be reporting to the Customer directly & his/her work and deliverables are tracked and managed by the Customer. This proposal contains proprietary and confidential information of Shellkode Proprietor and shall not be used, disclosed, or reproduced, in whole or in part, for any purpose other than to evaluate this proposal, without the prior written consent of authorized Shellkode personnel in and to this document and all information contained herein remains at all times in Shellkode.

Acceptance and Signatories to Statement of Work
Shellkode                                    WaterTec
Signature                                    Signature
Bhuvanesh CTO                                XXX
Date                                         Date`
  });

  // Clear form data when selected mode changes
  useEffect(() => {
    setFormData({
      generationMode: selectedMode || 'poc',
      companyName: '',
      authorOrganization: '',
      authorName: '',
      documentDate: new Date().toISOString().split('T')[0],
      projectObjective: '',
      uploadedFiles: []
    });
    setFileUploadError('');
    setSelectedSowSections(availableSowSectionIds(selectedMode || 'poc'));
    setHasPreviewGenerated(false);
    setInitialPopulationDone(false); // Reset auto-population flag
  }, [selectedMode]);

  // Smooth progress animation effect
  useEffect(() => {
    if (!isPreviewLoading) return;

    const interval = setInterval(() => {
      setPreviewProgress(current => {
        if (current < targetProgress) {
          // Increment by 1% every 200ms for smooth animation
          return Math.min(current + 1, targetProgress);
        }
        return current;
      });
    }, 200);

    return () => clearInterval(interval);
  }, [isPreviewLoading, targetProgress]);

  const isFormValid = useCallback((): boolean => {
    if (formData.generationMode === 'poc-to-production') {
      // For poc-to-production mode, only require uploaded files
      return formData.uploadedFiles !== undefined && formData.uploadedFiles.length > 0;
    } else {
      // For POC and Production modes, require all fields
      const companyNameValid = formData.companyName.trim() !== '' && 
                              formData.companyName.trim() !== 'Loading...' &&
                              formData.companyName.trim() !== 'Auto-populated from project context';
      
      return (
        companyNameValid &&
        formData.authorName.trim() !== '' &&
        formData.documentDate !== '' &&
        formData.projectObjective.trim() !== '' &&
        formData.projectObjective.trim().length >= MIN_OBJECTIVE_LENGTH
      );
    }
  }, [formData]);

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return `File "${file.name}" exceeds maximum size of 10MB`;
    }

    const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_FILE_TYPES.includes(fileExtension)) {
      return `File type "${fileExtension}" is not supported`;
    }

    return null;
  };

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  }, []);

  const handleFileUpload = useCallback((files: FileList | null) => {
    if (!files) return;

    setFileUploadError('');
    const newFiles = Array.from(files);
    const validFiles: File[] = [];
    const errors: string[] = [];

    newFiles.forEach(file => {
      const error = validateFile(file);
      if (error) {
        errors.push(error);
      } else {
        validFiles.push(file);
      }
    });

    if (errors.length > 0) {
      setFileUploadError(errors.join('; '));
    }

    if (validFiles.length > 0) {
      setFormData(prev => ({
        ...prev,
        uploadedFiles: [...(prev.uploadedFiles || []), ...validFiles]
      }));
    }
  }, []);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files);
    }
  }, [handleFileUpload]);

  const removeFile = useCallback((index: number) => {
    setFormData(prev => ({
      ...prev,
      uploadedFiles: prev.uploadedFiles?.filter((_, i) => i !== index) || []
    }));
  }, []);

  const handleGenerateSOW = async () => {
    if (!isFormValid()) {
      return;
    }

    // Check if preview_id exists (after preview generation)
    const previewId = localStorage.getItem('lastPreviewId');

    if (previewId) {
      // Prevent duplicate calls by checking if already generating
      if (isGenerating) {
        console.log('Already generating, skipping duplicate call');
        return;
      }

      // If preview_id exists, call finalize API (for standalone SOWs only)
      setIsGenerating(true);
      const toastId = toast.loading('Finalizing SOW document...', {
        position: 'top-right',
        autoClose: false,
      });

      try {
        console.log('Calling finalize API with preview_id:', previewId);
        const response = await apiService.finalizeSOW(previewId);
        console.log('Finalize API Response:', response);

        if (response.success) {
          // Clear preview_id IMMEDIATELY after successful call to prevent duplicates
          localStorage.removeItem('lastPreviewId');
          
          toast.update(toastId, {
            render: 'SOW finalized successfully!',
            type: 'success',
            isLoading: false,
            autoClose: 5000,
            closeButton: true,
          });
          
          // For project-based SOWs, call onSuccess to refresh the project page
          if (isProjectBased && onSuccess) {
            onSuccess();
          } else if (onGenerateSuccess) {
            onGenerateSuccess(formData);
          }
        } else {
          const errorMessage = response.error || response.message || 'Failed to finalize SOW';
          toast.update(toastId, {
            render: errorMessage,
            type: 'error',
            isLoading: false,
            autoClose: 5000,
            closeButton: true,
          });
          if (onGenerateError) {
            onGenerateError(errorMessage);
          }
        }
      } catch (error) {
        console.error('Finalize error:', error);
        const errorMessage = error instanceof Error ? error.message : 'Failed to finalize SOW';
        toast.update(toastId, {
          render: errorMessage,
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
        if (onGenerateError) {
          onGenerateError(errorMessage);
        }
      } finally {
        setIsGenerating(false);
      }
      return;
    }

    // No preview exists - this shouldn't happen if using the preview → finalize workflow
    // But handle it gracefully for backward compatibility
    if (isProjectBased && projectId) {
      // For project-based SOWs without preview, redirect to preview first
      toast.warning('Please generate a preview first before finalizing the SOW.', {
        position: 'top-right',
        autoClose: 5000,
      });
      return;
    }

    // For non-project-based SOWs, open modal for regular generation
    setShowModal(true);
  };

  const handleModalSave = async () => {
    if (!modalData.sowContent.trim()) {
      toast.error('SOW content cannot be empty');
      return;
    }

    setShowModal(false);
    setIsGenerating(true);
    const toastId = toast.loading('Generating SOW document...', {
      position: 'top-right',
      autoClose: false,
    });

    try {
      let response;

      // Check if this is project-based SOW creation
      if (isProjectBased && projectId) {
        console.log('Creating SOW for project:', projectId);

        // Map mode to uppercase for API
        const modeMap: { [key: string]: string } = {
          'poc': 'POC',
          'production': 'PROD',
          'poc-to-production': 'POC_TO_PROD'
        };

        // Determine the best company name to use
        const finalCompanyName = accountName || formData.companyName || projectName || 'Unknown Company';
        const finalProjectName = projectName || formData.authorOrganization || formData.companyName || 'Unknown Project';

        console.log('SOW Creation Data:', {
          mode: modeMap[formData.generationMode] || 'POC',
          objective: formData.projectObjective,
          customer_name: finalCompanyName,
          project_name: finalProjectName,
          author_name: formData.authorName || 'ShellKode'
        });

        // ✅ FIX: Use project-based API for ALL modes including POC_TO_PROD
        response = await apiService.createSOWForProject(projectId, {
          mode: modeMap[formData.generationMode] || 'POC',
          objective: formData.projectObjective,
          customer_name: finalCompanyName,
          project_name: finalProjectName,
          author_name: formData.authorName || 'ShellKode'
        });
      } else if (formData.generationMode === 'poc-to-production') {
        // For standalone (non-project) poc-to-production, use file upload method
        response = await apiService.generateSOWWithFiles(formData.uploadedFiles || []);
      } else {
        // For standalone (non-project) poc and production modes, use regular method
        response = await apiService.generateSOW(
          formData.authorName,
          formData.companyName,
          formData.generationMode,
          formData.projectObjective,
          formData.authorOrganization
        );
      }

      if (response.success) {
        toast.update(toastId, {
          render: isProjectBased ? 'SOW generation started! Check back in a few minutes.' : 'SOW generated successfully!',
          type: 'success',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });

        // If project-based and onSuccess callback exists, call it
        if (isProjectBased && onSuccess) {
          onSuccess();
        } else {
          onGenerateSuccess?.({ ...formData, selectedSowSections });
        }
      } else {
        const errorMessage = response.error || 'Failed to generate SOW';
        toast.update(toastId, {
          render: errorMessage,
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
        onGenerateError?.(errorMessage);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to generate SOW';
      toast.update(toastId, {
        render: errorMessage,
        type: 'error',
        isLoading: false,
        autoClose: 5000,
        closeButton: true,
      });
      onGenerateError?.(errorMessage);
    } finally {
      setIsGenerating(false);
    }
  };

  const handlePreview = async () => {
    if (!isFormValid()) {
      toast.error('Please fill in all required fields');
      return;
    }

    // Clear old preview data and close modal
    setPreviewData(null);
    setShowPreviewModal(false);
    setHasPreviewGenerated(false);

    // Show non-blocking toast notification instead of full-page loader
    const toastId = toast.loading('🎨 Starting preview generation...', {
      position: 'bottom-right',
      autoClose: false,
    });

    try {
      // Prepare data for preview API
      let companyName, projectName, authorName;
      
      if (isProjectBased) {
        // For project-based SOWs, use the auto-populated data
        companyName = accountName || formData.companyName || 'Unknown Company';
        projectName = formData.authorOrganization || 'Unknown Project';
        authorName = formData.authorName || 'ShellKode';
      } else {
        // For regular SOWs, use form data directly
        companyName = formData.companyName;
        projectName = formData.authorOrganization;
        authorName = formData.authorName;
      }

      console.log('Calling preview API with data:', {
        authorName,
        companyName,
        mode: formData.generationMode,
        objective: formData.projectObjective.substring(0, 100) + '...', // Log first 100 chars
        objectiveLength: formData.projectObjective.length,
        projectName,
        isProjectBased,
        selectedSowSections,
      });

      // Separate main file (for POC_TO_PROD) from supporting documents
      let mainFile: File | undefined;
      let supportingDocs: File[] = [];

      if (formData.generationMode === 'poc-to-production' && formData.uploadedFiles && formData.uploadedFiles.length > 0) {
        // First file is the main POC document
        mainFile = formData.uploadedFiles[0];
        // Rest are supporting documents
        supportingDocs = formData.uploadedFiles.slice(1);
      } else {
        // For POC and PROD modes, all files are supporting documents
        supportingDocs = formData.uploadedFiles || [];
      }

      console.log('Main file:', mainFile?.name);
      console.log('Supporting docs:', supportingDocs.map(f => f.name));

      // Call the preview API
      const response = await apiService.generatePreview(
        authorName,
        companyName,
        formData.generationMode,
        formData.projectObjective,
        projectName,
        mainFile,
        supportingDocs,
        isProjectBased ? projectId : undefined,
        isProjectBased ? accountId : undefined,
        selectedSowSections,
      );

      console.log('Preview API Response:', response);

      if (response.success && response.preview_id) {
        // Store preview_id in localStorage
        localStorage.setItem('lastPreviewId', response.preview_id);

        // Update toast to show it's processing in background
        toast.update(toastId, {
          render: '⚙️ Processing in background... You can continue working!',
          type: 'info',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });

        // Track progress with smart increments based on steps
        let currentProgressToast: any = null;
        const progressMap: { [key: string]: number } = {
          'Validating inputs': 10,
          'Extracting metadata': 15,
          'Retrieving RAG data': 20,
          'Retrieving POC RAG data': 20,
          'Retrieving PROD RAG data': 20,
          'Generating document': 30,
          'Researching': 35,
          'Research': 35,
          'Analyzing': 45,
          'Analyze': 45,
          'Validating': 55,
          'Validate': 55,
          'Generating content': 70,
          'Generate': 70,
          'Building document': 85,
          'Build': 85,
          'Document generated': 95,
          'Uploading': 98,
          'Completed': 100,
        };

        const getProgressFromStep = (step: string): number => {
          // Try exact match first
          if (progressMap[step]) return progressMap[step];

          // Try partial match
          for (const [key, value] of Object.entries(progressMap)) {
            if (step.toLowerCase().includes(key.toLowerCase())) {
              return value;
            }
          }

          // Default based on backend progress or 50%
          return 50;
        };

        // Start polling the status API every 10 seconds
        const pollInterval = setInterval(async () => {
          try {
            console.log('Polling status for preview_id:', response.preview_id);
            const statusResponse = await apiService.checkPreviewStatus(response.preview_id);
            console.log('Status API Response:', statusResponse);

            // Calculate smart progress based on current step
            let displayProgress = statusResponse.progress || 50;
            if (statusResponse.current_step) {
              const stepProgress = getProgressFromStep(statusResponse.current_step);
              // Use the higher of backend progress or step-based progress
              displayProgress = Math.max(displayProgress, stepProgress);
            }

            // Update or create progress toast
            if (statusResponse.current_step) {
              const progressMessage = `📊 Progress: ${displayProgress}% - ${statusResponse.current_step}`;

              if (currentProgressToast) {
                toast.update(currentProgressToast, {
                  render: progressMessage,
                  type: 'info',
                  autoClose: 5000,
                });
              } else {
                currentProgressToast = toast.info(progressMessage, {
                  position: 'bottom-right',
                  autoClose: 5000,
                });
              }
            }

            // Check for error conditions FIRST
            if (statusResponse.has_error || statusResponse.status === 'failed' || statusResponse.status === 'error') {
              // Stop polling on error
              clearInterval(pollInterval);

              const errorMsg = statusResponse.error || statusResponse.message || 'Preview generation failed';
              console.error('Preview generation failed:', {
                error: statusResponse.error,
                current_step: statusResponse.current_step,
                message: statusResponse.message,
                has_error: statusResponse.has_error,
                status: statusResponse.status,
                full_response: statusResponse
              });

              toast.error(`❌ Preview failed: ${errorMsg}`, {
                position: 'bottom-right',
                autoClose: 8000,
                closeButton: true,
              });

              // DO NOT show modal on error
              console.log('Preview failed. Not showing modal.');
              return; // Exit early to prevent any further processing
            }

            if (statusResponse.status === 'completed' || statusResponse.status === 'success' || statusResponse.status === 'ready') {
              // Verify content is actually populated (not just an empty object)
              const hasContent = (statusResponse.content && Object.keys(statusResponse.content).length > 0) ||
                                 (statusResponse.updated_content && Object.keys(statusResponse.updated_content).length > 0);

              if (!hasContent) {
                // Status is ready but content is empty — keep polling a few more times
                console.warn('Status is ready but content is empty, continuing to poll...');
                return; // don't stop interval, try again next tick
              }

              // Stop polling
              clearInterval(pollInterval);

              // Verify we have valid content before showing modal
              if (hasContent) {
                // Show success toast
                toast.success('✅ Preview ready! Opening editor...', {
                  position: 'bottom-right',
                  autoClose: 2000,
                  closeButton: true,
                });

                // Automatically set preview data and show modal
                setPreviewData(statusResponse);
                setShowPreviewModal(true);
                setHasPreviewGenerated(true);
              } else {
                toast.warning('⚠️ Preview completed but no content available', {
                  position: 'bottom-right',
                  autoClose: 5000,
                  closeButton: true,
                });
                console.warn('Preview completed but no content:', statusResponse);
              }
            }
          } catch (error) {
            console.error('Status polling error:', error);
            clearInterval(pollInterval);
            toast.error('❌ Failed to check preview status', {
              position: 'bottom-right',
              autoClose: 5000,
              closeButton: true,
            });
          }
        }, 10000); // Poll every 10 seconds

        // Set a timeout to stop polling after 5 minutes (safety measure)
        setTimeout(() => {
          clearInterval(pollInterval);
          toast.warning('⏱️ Preview timed out. Please try again.', {
            position: 'bottom-right',
            autoClose: 5000,
            closeButton: true,
          });
        }, 300000); // 5 minutes timeout

      } else {
        console.error('Preview API failed:', response);
        toast.update(toastId, {
          render: `❌ ${response.error || response.message || 'Failed to generate preview'}`,
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
      }
    } catch (error) {
      console.error('Preview error:', error);
      toast.update(toastId, {
        render: `❌ ${error instanceof Error ? error.message : 'Failed to generate preview'}`,
        type: 'error',
        isLoading: false,
        autoClose: 5000,
        closeButton: true,
      });
    }
  };

  const handleFinalizeFromPreview = async () => {
    const previewId = previewData?.preview_id || localStorage.getItem('lastPreviewId');

    if (!previewId) {
      toast.error('No preview ID found');
      return;
    }

    // Prevent duplicate calls
    if (isGenerating) {
      console.log('Already finalizing, skipping duplicate call');
      return;
    }

    setIsGenerating(true);
    const toastId = toast.loading('Finalizing SOW document...', {
      position: 'top-right',
      autoClose: false,
    });

    try {
      console.log('Calling finalize API with preview_id:', previewId);
      const response = await apiService.finalizeSOW(previewId);
      console.log('Finalize API Response:', response);

      if (response.success) {
        // Clear preview_id after successful finalization
        localStorage.removeItem('lastPreviewId');
        localStorage.removeItem('loadingFromDraft');

        toast.update(toastId, {
          render: '✅ SOW finalized and saved successfully!',
          type: 'success',
          isLoading: false,
          autoClose: 5000,
        });

        setShowPreviewModal(false);

        // If project-based, return to project page or call onSuccess
        if (isProjectBased && onSuccess) {
          setTimeout(() => {
            onSuccess();
          }, 1500);
        } else if (isProjectBased && projectId) {
          setTimeout(() => {
            navigate(`/projects/${projectId}`);
          }, 1500);
        }
      } else {
        toast.update(toastId, {
          render: `Failed to finalize: ${response.error || 'Unknown error'}`,
          type: 'error',
          isLoading: false,
          autoClose: 5000,
        });
      }
    } catch (error) {
      console.error('Finalize error:', error);
      toast.update(toastId, {
        render: `Failed to finalize: ${error instanceof Error ? error.message : 'Unknown error'}`,
        type: 'error',
        isLoading: false,
        autoClose: 5000,
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleEditFromPreview = async () => {
    const previewId = previewData?.preview_id || localStorage.getItem('lastPreviewId');

    if (!previewId) {
      toast.error('No preview ID found');
      return;
    }

    setShowPreviewModal(false);
    setEditData(previewData);
    setSelectedSections([]);
    setSectionInputs({});
    setIsFullReplace(false);
    setAvailableSections([]);
    setShowEditModal(true);

    // Call sections API based on current mode
    let mode: 'poc' | 'prod' | 'poc_to_prod';
    if (formData.generationMode === 'poc') {
      mode = 'poc';
    } else {
      // Both 'production' and 'poc-to-production' use 'prod'
      mode = 'prod';
    }
    
    const toastId = toast.loading('Loading sections...', {
      position: 'top-right',
      autoClose: false,
    });

    try {
      console.log(`Calling sections API for mode: ${mode}, previewId: ${previewId}`);
      const sectionsResponse = await apiService.fetchSections(mode, previewId);
      console.log('Sections API Response:', sectionsResponse);

      if (sectionsResponse.success && sectionsResponse.sections) {
        const sections = sectionsResponse.sections;

        setAvailableSections(sections);
        console.log('Available sections:', sections);

        toast.update(toastId, {
          render: 'Sections loaded successfully',
          type: 'success',
          isLoading: false,
          autoClose: 2000,
          closeButton: true,
        });
      } else {
        toast.update(toastId, {
          render: 'Sections loaded',
          type: 'info',
          isLoading: false,
          autoClose: 2000,
          closeButton: true,
        });
      }
    } catch (error) {
      console.error('Error fetching sections:', error);
      toast.update(toastId, {
        render: 'Failed to load sections',
        type: 'error',
        isLoading: false,
        autoClose: 3000,
        closeButton: true,
      });
    }
  };

  const handleSectionToggle = (section: string) => {
    setSelectedSections(prev => {
      if (prev.includes(section)) {
        const newSections = prev.filter(s => s !== section);
        setSectionInputs(prevInputs => {
          const newInputs = { ...prevInputs };
          delete newInputs[section];
          return newInputs;
        });
        return newSections;
      } else {
        return [...prev, section];
      }
    });
  };

  const handleSectionInputChange = (section: string, value: string) => {
    setSectionInputs(prev => ({
      ...prev,
      [section]: value
    }));
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>, section: string) => {
    // Allow default paste behavior - browser will handle it
    // This ensures bullet points, line breaks, and formatting are preserved
  };

  const handleSaveEdit = async () => {
    if (selectedSections.length === 0) {
      toast.error('Please select at least one section to edit');
      return;
    }

    const missingSections = selectedSections.filter(section => !sectionInputs[section]?.trim());
    if (missingSections.length > 0) {
      toast.error(`Please provide input for: ${missingSections.join(', ')}`);
      return;
    }

    const previewId = editData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) {
      toast.error('No preview ID found');
      return;
    }

    const toastId = toast.loading('Saving changes...', {
      position: 'top-right',
      autoClose: false,
    });

    try {
      const combinedInput = selectedSections.map(section => {
        return `[${section}]\n${sectionInputs[section]}`;
      }).join('\n\n');

      console.log('Calling edit API with:', {
        previewId,
        selectedSections,
        userInput: combinedInput,
        fullReplace: isFullReplace
      });

      const response = await apiService.editSOW(
        previewId,
        selectedSections,
        combinedInput,
        isFullReplace
      );

      console.log('Save Edit Response:', response);

      if (response.success) {
        toast.update(toastId, {
          render: `${selectedSections.length} section(s) updated successfully!`,
          type: 'success',
          isLoading: false,
          autoClose: 3000,
          closeButton: true,
        });

        setShowEditModal(false);
        setPreviewData(response);
        setShowPreviewModal(true);
        setSelectedSections([]);
        setSectionInputs({});
        
        // Scroll to first edited section after modal opens
        setTimeout(() => {
          if (response.edited_sections && response.edited_sections.length > 0) {
            const firstEditedSection = response.edited_sections[0];
            const element = document.getElementById(`section-${firstEditedSection}`);
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }
        }, 300);
      } else {
        toast.update(toastId, {
          render: response.error || response.message || 'Failed to save changes',
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
      }
    } catch (error) {
      console.error('Save edit error:', error);
      toast.update(toastId, {
        render: 'Failed to save changes',
        type: 'error',
        isLoading: false,
        autoClose: 5000,
        closeButton: true,
      });
    }
  };

  const isFormComplete = isFormValid();

  return (
    <div className="sow-generator-container">
      <div className="form-header">
        <div className="header-info">
          <h1 className="form-title">Create Statement of Work</h1>
          <p className="form-description">Fill in the details below to generate your professional SOW document</p>
        </div>
      </div>

      <div className="form-content">
        {formData.generationMode === 'poc-to-production' ? (
          // POC-to-Production mode - only show file upload
          <div className="section-group">
            <div className="section-header">
              <Upload className="section-icon" />
              <h2 className="section-title">Upload POC Documents</h2>
            </div>

            <SOWSectionChecklist
              mode={formData.generationMode}
              selected={selectedSowSections}
              onChange={setSelectedSowSections}
            />
            
            <div className="field-group full-width">
              <label className="field-label">POC Documents <span className="required">*</span></label>
              <div 
                className={`upload-area ${dragActive ? 'drag-active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                role="region"
                aria-label="File upload area"
              >
                <div className="upload-content">
                  <Upload className="upload-icon" />
                  <div className="upload-text">
                    <h3>Drop your POC documents here</h3>
                    <p>or <label htmlFor="file-input" className="upload-link">browse files</label> from your device</p>
                    <span className="upload-hint">Supports PDF, DOC, DOCX, TXT • Max 10MB per file</span>
                  </div>
                  <input
                    id="file-input"
                    type="file"
                    multiple
                    accept=".pdf,.doc,.docx,.txt"
                    onChange={(e) => handleFileUpload(e.target.files)}
                    className="file-input-hidden"
                    aria-label="Upload POC documents"
                  />
                </div>
              </div>

              {fileUploadError && (
                <div className="upload-error">
                  <AlertCircle className="error-icon" />
                  <span>{fileUploadError}</span>
                </div>
              )}

              {formData.uploadedFiles && formData.uploadedFiles.length > 0 && (
                <div className="uploaded-files">
                  <div className="files-header">
                    <span className="files-title">Uploaded Files ({formData.uploadedFiles.length})</span>
                  </div>
                  <div className="files-list">
                    {formData.uploadedFiles.map((file, index) => (
                      <div key={index} className="file-item">
                        <FileText className="file-icon" />
                        <div className="file-info">
                          <span className="file-name">
                            {file.name}
                            {formData.generationMode === 'poc-to-production' && index === 0 && (
                              <span className="file-badge" style={{ marginLeft: '8px', padding: '2px 8px', backgroundColor: '#4CAF50', color: 'white', borderRadius: '4px', fontSize: '11px' }}>
                                Main POC
                              </span>
                            )}
                            {formData.generationMode === 'poc-to-production' && index > 0 && (
                              <span className="file-badge" style={{ marginLeft: '8px', padding: '2px 8px', backgroundColor: '#2196F3', color: 'white', borderRadius: '4px', fontSize: '11px' }}>
                                Supporting
                              </span>
                            )}
                            {formData.generationMode !== 'poc-to-production' && (
                              <span className="file-badge" style={{ marginLeft: '8px', padding: '2px 8px', backgroundColor: '#2196F3', color: 'white', borderRadius: '4px', fontSize: '11px' }}>
                                Supporting
                              </span>
                            )}
                          </span>
                          <span className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeFile(index)}
                          className="file-remove-btn"
                          aria-label={`Remove ${file.name}`}
                          title={`Remove ${file.name}`}
                        >
                          <X className="remove-icon" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Smart Single Button for POC_TO_PROD */}
            <div className="button-container" style={{ marginTop: '24px' }}>
              <button
                onClick={hasPreviewGenerated ? handleGenerateSOW : handlePreview}
                disabled={!isFormComplete || isGenerating}
                className={`smart-generate-button ${isGenerating ? 'generating' : ''} ${!isFormComplete ? 'disabled' : ''}`}
                aria-busy={isGenerating}
                aria-label={
                  isGenerating
                    ? 'Crafting your document...'
                    : hasPreviewGenerated
                      ? 'Finalize and deliver'
                      : 'Craft SOW Document'
                }
                title={
                  !isFormComplete
                    ? 'Please upload POC document'
                    : isGenerating
                      ? 'Creating your professional SOW...'
                      : hasPreviewGenerated
                        ? 'Click to finalize and download your document'
                        : 'Click to preview and craft your SOW'
                }
              >
                {isGenerating ? (
                  <>
                    <div className="spinner-icon"></div>
                    <span className="button-text">
                      🎨 Crafting Your Document...
                    </span>
                  </>
                ) : (
                  <>
                    <Wand2 className="button-icon" />
                    <span className="button-text">
                      {hasPreviewGenerated ? '🚀 Finalize & Deliver' : '✨ Craft SOW Document'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          // POC and Production modes - show all input fields
          <>
            <div className="section-group">
              <div className="section-header">
                <h2 className="section-title">Organization Information</h2>
              </div>
              
              <div className="fields-grid">
                <div className="field-group">
                  <label htmlFor="companyName" className="field-label">
                    Company Name <span className="required">*</span>
                    {isProjectBased && (
                      <span className="auto-populated-indicator" title="Auto-populated from account/project">
                        ✓ Auto-filled
                      </span>
                    )}
                  </label>
{isProjectBased ? (
                    <select
                      id="companyName"
                      name="companyName"
                      value={formData.companyName}
                      onChange={handleInputChange}
                      className={`field-input ${formData.companyName ? 'auto-populated' : ''}`}
                      title="Select the account/company for this SOW"
                    >
                      {!formData.companyName && <option value="">Select company...</option>}
                      {accountName && <option value={accountName}>{accountName}</option>}
                      {projectName && projectName !== accountName && (
                        <option value={projectName}>{projectName} (from project)</option>
                      )}
                      {!accountName && !projectName && <option value="">Loading...</option>}
                    </select>
                  ) : (
                    <input
                      type="text"
                      id="companyName"
                      name="companyName"
                      value={formData.companyName}
                      onChange={handleInputChange}
                      placeholder="Enter company name"
                      className="field-input"
                    />
                  )}
                </div>

                <div className="field-group">
                  <label htmlFor="authorName" className="field-label">
                    Author Name <span className="required">*</span>
                  </label>
                  <div className="input-with-icon">
                    <input
                      type="text"
                      id="authorName"
                      name="authorName"
                      value={formData.authorName}
                      onChange={handleInputChange}
                      placeholder="Enter author name"
                      className="field-input with-icon"
                    />
                    <User className="field-icon" />
                  </div>
                </div>

                <div className="field-group">
                  <label htmlFor="authorOrganization" className="field-label">
                    Project Name <span className="required">*</span>
                    {isProjectBased && projectName && (
                      <span className="auto-populated-indicator" title="Auto-populated from project (editable)">
                        ✓ Auto-filled
                      </span>
                    )}
                  </label>
                  <input
                    type="text"
                    id="authorOrganization"
                    name="authorOrganization"
                    value={formData.authorOrganization}
                    onChange={handleInputChange}
                    placeholder={isProjectBased ? "Auto-populated from project (editable)" : "Enter project name"}
                    className={`field-input ${isProjectBased && projectName ? 'auto-populated' : ''}`}
                    title={isProjectBased && projectName ? `Auto-populated from project: ${projectName} (you can edit this)` : ''}
                  />
                </div>

                <div className="field-group">
                  <label htmlFor="documentDate" className="field-label">
                    Document Date <span className="required">*</span>
                  </label>
                  <div className="date-picker-wrapper">
                    <DatePicker
                      selected={formData.documentDate ? new Date(formData.documentDate) : null}
                      onChange={(date: Date | null) => {
                        if (date) {
                          const year = date.getFullYear();
                          const month = String(date.getMonth() + 1).padStart(2, '0');
                          const day = String(date.getDate()).padStart(2, '0');
                          setFormData(prev => ({
                            ...prev,
                            documentDate: `${year}-${month}-${day}`
                          }));
                        }
                      }}
                      maxDate={new Date()}
                      dateFormat="yyyy-MM-dd"
                      placeholderText="Select document date"
                      className="field-input date-picker-input"
                      wrapperClassName="date-picker-full-width"
                      showYearDropdown
                      showMonthDropdown
                      dropdownMode="select"
                    />
                    <Calendar className="date-picker-icon" size={16} />
                  </div>
                </div>
              </div>
            </div>

            <div className="section-divider"></div>

            <div className="section-group">
              <div className="section-header">
                <h2 className="section-title">Project Details</h2>
              </div>

              <SOWSectionChecklist
                mode={formData.generationMode}
                selected={selectedSowSections}
                onChange={setSelectedSowSections}
              />
              
              {/* Project Objectives - Full Width */}
              <div className="field-group full-width">
                <label htmlFor="projectObjective" className="field-label">
                  Project Objectives & Goals <span className="required">*</span>
                </label>
                <textarea
                  id="projectObjective"
                  name="projectObjective"
                  value={formData.projectObjective}
                  onChange={handleInputChange}
                  placeholder="Describe your project objectives, deliverables, timeline, and expected outcomes in detail..."
                  className="field-textarea"
                  rows={5}
                  style={{
                    height: '120px',
                    minHeight: '120px',
                    maxHeight: '120px',
                    resize: 'none'
                  }}
                />
                <div className="textarea-info">
                  <span className="char-count">
                    {formData.projectObjective.length} / {MIN_OBJECTIVE_LENGTH} characters (minimum)
                  </span>
                </div>
              </div>

              {/* Supporting Documents - Full Width Below */}
              <div className="field-group full-width" style={{ marginTop: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <Upload className="section-icon" style={{ width: '20px', height: '20px' }} />
                  <label className="field-label" style={{ marginBottom: 0 }}>Business Requirement & Other Supporting Documents (Optional)</label>
                </div>
                <p style={{ fontSize: '14px', color: '#666', marginBottom: '12px', marginTop: '4px' }}>
                  Upload additional documents for context (optional)
                </p>
                <div
                  className={`upload-area ${dragActive ? 'drag-active' : ''}`}
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  role="region"
                  aria-label="Supporting documents upload area"
                >
                  <div className="upload-content">
                    <Upload className="upload-icon" />
                    <div className="upload-text">
                      <h3>Drop supporting documents here</h3>
                      <p>or <label htmlFor="file-input-support" className="upload-link">browse files</label> from your device</p>
                      <span className="upload-hint">Supports PDF, DOC, DOCX, TXT • Max 10MB per file</span>
                    </div>
                    <input
                      id="file-input-support"
                      type="file"
                      multiple
                      accept=".pdf,.doc,.docx,.txt"
                      onChange={(e) => handleFileUpload(e.target.files)}
                      className="file-input-hidden"
                      aria-label="Upload supporting documents"
                    />
                  </div>
                </div>

                {fileUploadError && (
                  <div className="upload-error">
                    <AlertCircle className="error-icon" />
                    <span>{fileUploadError}</span>
                  </div>
                )}

                {formData.uploadedFiles && formData.uploadedFiles.length > 0 && (
                  <div className="uploaded-files">
                    <div className="files-header">
                      <span className="files-title">Supporting Documents ({formData.uploadedFiles.length})</span>
                    </div>
                    <div className="files-list">
                      {formData.uploadedFiles.map((file, index) => (
                        <div key={index} className="file-item">
                          <FileText className="file-icon" />
                          <div className="file-info">
                            <span className="file-name">{file.name}</span>
                            <span className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeFile(index)}
                            className="file-remove-btn"
                            aria-label={`Remove ${file.name}`}
                            title={`Remove ${file.name}`}
                          >
                            <X className="remove-icon" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Smart Single Button for POC/PROD */}
            <div className="button-container" style={{ marginTop: '24px' }}>
              <button
                onClick={hasPreviewGenerated ? handleGenerateSOW : handlePreview}
                disabled={!isFormComplete || isGenerating}
                className={`smart-generate-button ${isGenerating ? 'generating' : ''} ${!isFormComplete ? 'disabled' : ''}`}
                aria-busy={isGenerating}
                aria-label={
                  isGenerating
                    ? 'Crafting your document...'
                    : hasPreviewGenerated
                      ? 'Finalize and deliver'
                      : 'Craft SOW Document'
                }
                title={
                  !isFormComplete
                    ? 'Please fill in all required fields'
                    : isGenerating
                      ? 'Creating your professional SOW...'
                      : hasPreviewGenerated
                        ? 'Click to finalize and download your document'
                        : 'Click to preview and craft your SOW'
                }
              >
                {isGenerating ? (
                  <>
                    <div className="spinner-icon"></div>
                    <span className="button-text">
                      🎨 Crafting Your Document...
                    </span>
                  </>
                ) : (
                  <>
                    <Wand2 className="button-icon" />
                    <span className="button-text">
                      {hasPreviewGenerated ? '🚀 Finalize & Deliver' : '✨ Craft SOW Document'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Modal — rendered in portal so it's never clipped by overflow parents */}
      {showModal && ReactDOM.createPortal(
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Statement of Work Content</h2>
              <button className="modal-close" onClick={() => setShowModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="modal-field">
                <label htmlFor="modal-sow-content">SOW Document Content</label>
                <textarea
                  id="modal-sow-content"
                  value={modalData.sowContent}
                  onChange={(e) => setModalData(prev => ({ ...prev, sowContent: e.target.value }))}
                  placeholder="Enter SOW content..."
                  className="modal-textarea"
                  rows={20}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={handleModalSave}>
                Update
              </button>
              <button className="modal-btn modal-btn-primary" onClick={handleModalSave}>
                Save
              </button>
            </div>
          </div>
        </div>
      , document.body)}

      {/* Preview Modal — portal to avoid overflow clipping */}
      {showPreviewModal && previewData && ReactDOM.createPortal(
        <div className="modal-overlay" onClick={() => setShowPreviewModal(false)}>
          <div className="modal-content modal-large preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>SOW Preview</h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                {isProjectBased && projectId && (
                  <button
                    className="btn-secondary"
                    onClick={() => navigate(`/projects/${projectId}`)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '10px 20px',
                      fontSize: '0.875rem'
                    }}
                  >
                    <ArrowLeft size={16} />
                    Return to Project
                  </button>
                )}
                <button className="modal-close" onClick={() => setShowPreviewModal(false)}>
                  <X size={20} />
                </button>
              </div>
            </div>
            <div className="modal-body preview-body">
              {previewData.error && (
                <div className="preview-error">
                  <strong>Error:</strong> {previewData.error}
                </div>
              )}

              {(previewData.current_step || previewData.progress !== undefined) && (
                <div className="preview-status-card">
                  {previewData.progress !== undefined && (
                    <div className="progress-section">
                      <div className="progress-header">
                        <span className="progress-label">Generation Progress</span>
                        <span className="progress-percentage">{previewData.progress}%</span>
                      </div>
                      <div className="progress-bar-container">
                        <div 
                          className="progress-bar-fill" 
                          style={{ width: `${previewData.progress}%` }}
                        ></div>
                      </div>
                    </div>
                  )}
                  
                  {previewData.current_step && (
                    <div className="current-step-section">
                      <div className="step-icon">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="2"/>
                          <circle cx="8" cy="8" r="3" fill="currentColor"/>
                        </svg>
                      </div>
                      <div className="step-content">
                        <span className="step-label">Current Step</span>
                        <span className="step-text">{previewData.current_step}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <h3 className="preview-section-title">Document Information</h3>
              <div className="preview-info-grid">
                <div className="preview-info-row">
                  <span className="preview-label">Mode:</span>
                  <span className="preview-value">{previewData.mode || 'N/A'}</span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Company Name:</span>
                  <span className="preview-value">
                    {previewData.metadata?.company_name || previewData.company_name || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Project Title:</span>
                  <span className="preview-value">
                    {previewData.metadata?.project_title || previewData.project_title || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Author Name:</span>
                  <span className="preview-value">
                    {previewData.metadata?.author_name || previewData.author_name || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Author Organization:</span>
                  <span className="preview-value">
                    {previewData.metadata?.author_org || previewData.author_org || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Document Date:</span>
                  <span className="preview-value">
                    {previewData.metadata?.document_date || previewData.document_date || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Start Date:</span>
                  <span className="preview-value">
                    {previewData.metadata?.start_date || previewData.start_date || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">End Date:</span>
                  <span className="preview-value">
                    {previewData.metadata?.end_date || previewData.end_date || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Version:</span>
                  <span className="preview-value">
                    {previewData.metadata?.version || previewData.version || 'N/A'}
                  </span>
                </div>
                <div className="preview-info-row">
                  <span className="preview-label">Timezone:</span>
                  <span className="preview-value">
                    {previewData.metadata?.timezone || previewData.timezone || 'N/A'}
                  </span>
                </div>
              </div>

              {(previewData.metadata?.author_org_description || previewData.author_org_description) && (
                <>
                  <h3 className="preview-section-title">Organization Description</h3>
                  <p className="preview-description">
                    {previewData.metadata?.author_org_description || previewData.author_org_description}
                  </p>
                </>
              )}

              {/* Display content if available and non-empty */}
              {previewData.content && (
                typeof previewData.content === 'string'
                  ? previewData.content.length > 0
                  : Object.keys(previewData.content).length > 0
              ) && (
                <>
                  <h3 className="preview-section-title">Document Sections</h3>
                  <div className="preview-content-display">
                    {typeof previewData.content === 'string' ? (
                      <pre className="preview-content-text">{previewData.content}</pre>
                    ) : (
                      <div className="preview-content-sections">
                        {Object.entries(previewData.content).map(([section, content]) => {
                          const isEdited = previewData.edited_sections && previewData.edited_sections.includes(section);
                          return (
                            <div
                              key={section}
                              id={`section-${section}`}
                              className={`preview-content-section ${isEdited ? 'edited-section' : ''}`}
                            >
                              <div className="preview-content-section-title">
                                <h4>{section.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</h4>
                                {isEdited && <span className="edited-badge">Edited</span>}
                              </div>
                              <p className="preview-content-section-text">{String(content)}</p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Display updated_content (after edits) if available and non-empty */}
              {previewData.updated_content && Object.keys(previewData.updated_content).length > 0 && (
                <>
                  <h3 className="preview-section-title">Document Sections</h3>
                  <div className="preview-content-display">
                    <div className="preview-content-sections">
                      {Object.entries(previewData.updated_content).map(([section, content]) => {
                        const isEdited = previewData.edited_sections && previewData.edited_sections.includes(section);
                        return (
                          <div
                            key={section}
                            id={`section-${section}`}
                            className={`preview-content-section ${isEdited ? 'edited-section' : ''}`}
                          >
                            <div className="preview-content-section-title">
                              <h4>{section.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</h4>
                              {isEdited && <span className="edited-badge">Edited</span>}
                            </div>
                            <p className="preview-content-section-text">{String(content)}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}

              {/* Show empty-content diagnostic if neither content block has data */}
              {(!previewData.content || Object.keys(previewData.content || {}).length === 0) &&
               (!previewData.updated_content || Object.keys(previewData.updated_content || {}).length === 0) &&
               previewData.status === 'ready' && (
                <div style={{ padding: '16px', background: 'var(--warning-bg)', border: '1px solid rgba(181,71,8,0.2)', borderRadius: '8px', fontSize: '13px', color: 'var(--warning)' }}>
                  Preview is ready but the generated content appears to be empty. This may indicate a template configuration issue. Try regenerating the document.
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowPreviewModal(false)}>
                Close
              </button>
              <button className="modal-btn modal-btn-primary" onClick={handleEditFromPreview}>
                <Edit size={16} style={{ marginRight: '8px' }} />
                Edit Content
              </button>
              <button
                className="modal-btn modal-btn-success"
                onClick={handleFinalizeFromPreview}
                disabled={isGenerating}
                style={{
                  background: isGenerating ? '#94a3b8' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  cursor: isGenerating ? 'not-allowed' : 'pointer'
                }}
              >
                {isGenerating ? (
                  <>
                    <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
                    Finalizing...
                  </>
                ) : (
                  <>
                    <Wand2 size={16} style={{ marginRight: '8px' }} />
                    Finalize & Save
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      , document.body)}

      {/* Edit Modal — portal */}
      {showEditModal && editData && ReactDOM.createPortal(
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content modal-large edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Edit SOW Sections</h2>
              <button className="modal-close" onClick={() => setShowEditModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body edit-body">
              {/* Edit Mode Toggle */}
              <div className="edit-mode-toggle-container" style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px',
                background: '#f9fafb',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                marginBottom: '20px',
                gap: '16px',
                minHeight: '60px',
                width: '100%'
              }}>
                <div className="edit-mode-info" style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  flex: 1
                }}>
                  <label className="edit-mode-label" style={{
                    fontSize: '14px',
                    fontWeight: 600,
                    color: '#374151',
                    margin: 0
                  }}>Edit Mode:</label>
                  <span className="edit-mode-description" style={{
                    fontSize: '13px',
                    color: '#6b7280',
                    lineHeight: 1.4
                  }}>
                    {isFullReplace 
                      ? 'Full Edit - Completely replace section content' 
                      : 'Partial Edit - Make incremental changes to content'}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    console.log('Toggle clicked! Current state:', isFullReplace);
                    setIsFullReplace(!isFullReplace);
                  }}
                  className={`toggle-button ${isFullReplace ? 'active' : ''}`}
                  aria-pressed={isFullReplace}
                  title={isFullReplace ? 'Switch to Partial Edit' : 'Switch to Full Edit'}
                  style={{
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: isFullReplace ? '8px 60px 8px 16px' : '8px 16px 8px 60px',
                    background: isFullReplace ? '#dbeafe' : '#e5e7eb',
                    border: isFullReplace ? '2px solid #3b82f6' : '2px solid #d1d5db',
                    borderRadius: '24px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: 600,
                    color: isFullReplace ? '#1e40af' : '#6b7280',
                    whiteSpace: 'nowrap'
                  }}
                >
                  <span className="toggle-slider" style={{
                    position: 'absolute',
                    left: isFullReplace ? 'auto' : '4px',
                    right: isFullReplace ? '4px' : 'auto',
                    width: '44px',
                    height: '28px',
                    background: isFullReplace ? '#3b82f6' : '#9ca3af',
                    borderRadius: '20px',
                    boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.1)'
                  }}>
                    <span style={{
                      position: 'absolute',
                      top: '2px',
                      left: isFullReplace ? '18px' : '2px',
                      width: '24px',
                      height: '24px',
                      background: 'white',
                      borderRadius: '50%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)'
                    }}></span>
                  </span>
                  <span className="toggle-label" style={{ userSelect: 'none' }}>
                    {isFullReplace ? 'Full Edit' : 'Partial Edit'}
                  </span>
                </button>
              </div>

              <div className="multi-section-selector">
                <label className="section-label">Select Sections to Edit:</label>
                <div className="sections-checkbox-list">
                  {availableSections.length === 0 ? (
                    <p style={{ color: '#6b7280', fontSize: '14px', padding: '8px 0' }}>Loading sections...</p>
                  ) : (
                    availableSections.map((section) => (
                      <label key={section.key} className="section-checkbox-item">
                        <input
                          type="checkbox"
                          checked={selectedSections.includes(section.key)}
                          onChange={() => handleSectionToggle(section.key)}
                          className="section-checkbox"
                        />
                        <span className="section-checkbox-label">{section.name}</span>
                      </label>
                    ))
                  )}
                </div>
              </div>

              {selectedSections.length > 0 && (
                <div className="selected-sections-inputs">
                  {selectedSections.map((section) => (
                    <div key={section} className="section-input-group">
                      <div className="section-input-header">
                        <h4 className="section-input-title">{availableSections.find(s => s.key === section)?.name || section}</h4>
                        <button
                          type="button"
                          onClick={() => handleSectionToggle(section)}
                          className="remove-section-btn"
                          title="Remove section"
                        >
                          <X size={14} />
                        </button>
                      </div>
                      
                      <div className="current-content-compact">
                        <span className="content-label">Current:</span>
                        <div className="content-preview">
                          {((editData?.content || editData?.updated_content)?.[section] || '').substring(0, 100)}...
                        </div>
                      </div>

                      <textarea
                        value={sectionInputs[section] || ''}
                        onChange={(e) => handleSectionInputChange(section, e.target.value)}
                        onPaste={(e) => handlePaste(e, section)}
                        placeholder={
                          isFullReplace 
                            ? `Enter complete new content for ${section}...` 
                            : `Describe changes for ${section} (e.g., "Add another week in the timeline")...`
                        }
                        className="section-input-textarea"
                        rows={4}
                        style={{
                          whiteSpace: 'pre-wrap',
                          wordWrap: 'break-word',
                          fontFamily: 'inherit'
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}

              {selectedSections.length === 0 && (
                <div className="no-selection-message">
                  <p>Please select at least one section to edit</p>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowEditModal(false)}>
                Close
              </button>
              <button 
                className="modal-btn modal-btn-primary" 
                onClick={handleSaveEdit}
                disabled={selectedSections.length === 0}
              >
                <Edit size={16} style={{ marginRight: '8px' }} />
                Save {selectedSections.length > 0 && `(${selectedSections.length})`}
              </button>
            </div>
          </div>
        </div>
      , document.body)}

      {/* Full-page loader for preview generation */}
      {/* Removed blocking preview loader - now using non-blocking toast notifications */}
    </div>
  );
};

export default SOWGenerator;
