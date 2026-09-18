import React, { useState, useCallback, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Wand2, User, Calendar, Upload, FileText, X, AlertCircle, Eye, Edit, ArrowLeft, Loader } from 'lucide-react';
import { toast } from '../utils/toast';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import apiService from '../services/apiService';
import SOWSectionChecklist from './SOWSectionChecklist';
import { hasProjectScopeSource } from './sowInputValidation';
import DiagramEditorModal, { ArchitectureDiagramAsset } from './DiagramEditorModal';
import {
  EditableMarkdownSection,
  getEffectivePreviewContent,
  isPreviewBodyKey,
  MarkdownRenderer,
  parsePreviewContentMarkdown,
  previewSectionLabel,
  serializePreviewContent,
} from './SOWPreviewMarkdown';
import './SOWGenerator.css';
import { BUSINESS_UNITS, useAuth } from '../contexts/AuthContext';

interface SOWGeneratorData {
  generationMode: 'poc' | 'production' | 'poc-to-production';
  companyName: string;
  authorOrganization: string;
  authorName: string;
  documentDate: string;
  projectObjective: string;
  uploadedFiles?: File[];
  selectedSowSections?: string[];
  businessUnit?: string;
  pricingRegion?: string;
  pricingIncludeProposed?: boolean;
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
const ALLOWED_FILE_TYPES = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt'];

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
  const { user, isAdmin } = useAuth();
  const selectableBusinessUnits = isAdmin ? BUSINESS_UNITS : (user?.business_units || []);
  const canSelectBusinessUnit = isAdmin || selectableBusinessUnits.length > 1;

  // If projectId is provided, use it for project-based SOW creation
  const isProjectBased = !!projectId;

  const [formData, setFormData] = useState<SOWGeneratorData>({
    generationMode: selectedMode || 'poc',
    companyName: accountName || '',
    authorOrganization: isProjectBased ? (projectName || '') : 'ShellKode',
    authorName: '',
    documentDate: new Date().toISOString().split('T')[0],
    projectObjective: '',
    uploadedFiles: [],
    businessUnit: user?.business_unit || '',
    pricingRegion: '',
    pricingIncludeProposed: true,
  });
  // Starts empty — the user builds up the SOW section order deliberately
  // rather than starting from an implicit "everything included" state.
  const [selectedSowSections, setSelectedSowSections] = useState<string[]>([]);

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
        console.log('Auto-populating company name:', newCompanyName);
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
        console.log('Auto-populating project name:', newProjectName);
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
    console.log('SOWGenerator - Props changed:', { accountName, projectName, isProjectBased });
    
    if (isProjectBased && accountName && (!formData.companyName || formData.companyName === '')) {
      console.log('Auto-populating company name with:', accountName);
      setFormData(prev => ({
        ...prev,
        companyName: accountName
      }));
      
      toast.success('Company name auto-populated from account', {
        position: 'bottom-right',
        autoClose: 2000,
      });
    }
    
    if (isProjectBased && projectName && (!formData.authorOrganization || formData.authorOrganization === '' || formData.authorOrganization === 'ShellKode')) {
      console.log('Auto-populating project name with:', projectName);
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
  const [diagramEditorAsset, setDiagramEditorAsset] = useState<{asset: ArchitectureDiagramAsset; index: number} | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState<any>(null);
  const [markdownDraft, setMarkdownDraft] = useState('');
  const [editableMarkdownSections, setEditableMarkdownSections] = useState<EditableMarkdownSection[]>([]);
  const [isSavingMarkdown, setIsSavingMarkdown] = useState(false);
  const [isRecalculatingPricing, setIsRecalculatingPricing] = useState(false);
  const [hasPreviewGenerated, setHasPreviewGenerated] = useState(false);
  // React state updates are asynchronous, so a rapid second click can arrive
  // before isGenerating is rendered. This ref closes that race immediately.
  const generationLockRef = useRef(false);
  const acquireGenerationLock = () => {
    if (generationLockRef.current) return false;
    generationLockRef.current = true;
    setIsGenerating(true);
    return true;
  };
  const releaseGenerationLock = () => {
    generationLockRef.current = false;
    setIsGenerating(false);
  };

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
            console.log('Draft preview loaded and ready:', statusResponse);
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

            // Keep draft recovery bounded while allowing longer source-backed runs.
            setTimeout(() => clearInterval(pollInterval), 600000);
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
Objective                                                                                          
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
WaterTec provides water-management solutions for commercial and industrial applications.

For this illustrative SOW, its relevant context is the use of filtration, treatment, and monitoring capabilities to support operational efficiency.

Objective
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
      uploadedFiles: [],
      businessUnit: user?.business_unit || '',
      pricingRegion: '',
      pricingIncludeProposed: true,
    });
    setFileUploadError('');
    setSelectedSowSections([]);
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
    if (selectedSowSections.length === 0) return false;
    if (!formData.businessUnit) return false;

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
        formData.authorOrganization.trim() !== '' &&
        formData.documentDate !== '' &&
        hasProjectScopeSource(formData.projectObjective, formData.uploadedFiles)
      );
    }
  }, [formData, selectedSowSections]);

  const getMissingFormFields = useCallback((): string[] => {
    const missing: string[] = [];
    if (selectedSowSections.length === 0) missing.push('at least one SOW section');
    if (!formData.businessUnit) {
      missing.push(canSelectBusinessUnit ? 'SOW owner/business unit' : 'business unit assignment for your profile');
    }
    if (formData.generationMode === 'poc-to-production') {
      if (!formData.uploadedFiles?.length) missing.push('a POC document');
      return missing;
    }
    if (!formData.companyName.trim() || ['Loading...', 'Auto-populated from project context'].includes(formData.companyName.trim())) {
      missing.push('company name');
    }
    if (!formData.authorName.trim()) missing.push('author name');
    if (!formData.authorOrganization.trim()) missing.push('project name');
    if (!formData.documentDate) missing.push('document date');
    if (!hasProjectScopeSource(formData.projectObjective, formData.uploadedFiles)) {
      missing.push('a supporting document or additional details');
    }
    return missing;
  }, [formData, canSelectBusinessUnit, selectedSowSections]);

  const showMissingFields = useCallback(() => {
    const missing = getMissingFormFields();
    if (missing.length) {
      toast.error(`Please provide: ${missing.join(', ')}.`, {
        position: 'top-right',
        autoClose: 6000,
      });
    }
  }, [getMissingFormFields]);

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return `File "${file.name}" exceeds maximum size of 10MB`;
    }

    const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_FILE_TYPES.includes(fileExtension)) {
      return 'Unsupported file type. Supported files: PDF, Word, Excel, and TXT.';
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
      showMissingFields();
      return;
    }

    // Check if preview_id exists (after preview generation)
    const previewId = localStorage.getItem('lastPreviewId');

    if (previewId) {
      if (!acquireGenerationLock()) {
        console.log('Already generating, skipping duplicate call');
        return;
      }

      // If preview_id exists, call finalize API (for standalone SOWs only)
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
        releaseGenerationLock();
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

    if (!acquireGenerationLock()) return;
    setShowModal(false);
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
      releaseGenerationLock();
    }
  };

  const handlePreview = async () => {
    if (!isFormValid()) {
      showMissingFields();
      return;
    }

    if (!acquireGenerationLock()) {
      console.log('Preview generation already in progress, skipping duplicate call');
      return;
    }

    // Clear old preview data and close modal
    setPreviewData(null);
    setShowPreviewModal(false);
    setHasPreviewGenerated(false);

    // Show non-blocking toast notification instead of full-page loader
    const toastId = toast.loading('Starting preview generation...', {
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
        businessUnit: formData.businessUnit,
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
        formData.businessUnit,
        {
          region: formData.pricingRegion,
          includeProposed: formData.pricingIncludeProposed,
        },
      );

      console.log('Preview API Response:', response);

      if (response.success && response.preview_id) {
        // Store preview_id in localStorage
        localStorage.setItem('lastPreviewId', response.preview_id);

        // Update toast to show it's processing in background
        toast.update(toastId, {
          render: 'Processing preview in the background...',
          type: 'info',
          isLoading: true,
          autoClose: false,
          closeButton: false,
        });

        // Report only backend milestones and completed-section counts. The
        // backend owns the percentage; the UI must not fabricate progress.
        // Keep one persistent toast for the whole job. A short-lived toast can
        // disappear during a long LLM step while polling continues with a stale ID.
        let currentProgressToast: any = toastId;
        let pollInterval: ReturnType<typeof setInterval> | null = null;
        let safetyTimeout: ReturnType<typeof setTimeout> | null = null;
        let pollingFinished = false;
        const stopPolling = () => {
          if (pollingFinished) return;
          pollingFinished = true;
          if (pollInterval) clearInterval(pollInterval);
          if (safetyTimeout) clearTimeout(safetyTimeout);
          releaseGenerationLock();
        };

        const pollPreviewStatus = async () => {
          if (pollingFinished) return;
          try {
            console.log('Polling status for preview_id:', response.preview_id);
            const statusResponse = await apiService.checkPreviewStatus(response.preview_id);
            console.log('Status API Response:', statusResponse);

            const displayProgress = Number(statusResponse.progress ?? 0);

            // Update or create progress toast
            if (statusResponse.current_step) {
              const progressMessage = `Progress: ${displayProgress}% - ${statusResponse.current_step}`;

              if (currentProgressToast) {
                toast.update(currentProgressToast, {
                  render: progressMessage,
                  type: 'info',
                  isLoading: true,
                  autoClose: false,
                  closeButton: false,
                });
              } else {
                currentProgressToast = toast.info(progressMessage, {
                  position: 'bottom-right',
                  autoClose: false,
                  isLoading: true,
                  closeButton: false,
                });
              }
            }

            // Check for error conditions FIRST
            if (statusResponse.has_error || statusResponse.status === 'failed' || statusResponse.status === 'error') {
              // Stop polling on error
              stopPolling();

              const errorMsg = statusResponse.error || statusResponse.message || 'Preview generation failed';
              console.error('Preview generation failed:', {
                error: statusResponse.error,
                current_step: statusResponse.current_step,
                message: statusResponse.message,
                has_error: statusResponse.has_error,
                status: statusResponse.status,
                full_response: statusResponse
              });

              toast.update(currentProgressToast, {
                render: `Preview failed: ${errorMsg}`,
                type: 'error',
                isLoading: false,
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
              stopPolling();

              // Verify we have valid content before showing modal
              if (hasContent) {
                // Show success toast
                toast.update(currentProgressToast, {
                  render: 'Preview ready. Opening editor...',
                  type: 'success',
                  isLoading: false,
                  autoClose: 2000,
                  closeButton: true,
                });

                // Automatically set preview data and show modal
                setPreviewData(statusResponse);
                setShowPreviewModal(true);
                setHasPreviewGenerated(true);
              } else {
                toast.update(currentProgressToast, {
                  render: 'Preview completed but no content is available',
                  type: 'warning',
                  isLoading: false,
                  autoClose: 5000,
                  closeButton: true,
                });
                console.warn('Preview completed but no content:', statusResponse);
              }
            }
          } catch (error) {
            console.error('Status polling error:', error);
            stopPolling();
            toast.update(currentProgressToast, {
              render: 'Failed to check preview status',
              type: 'error',
              isLoading: false,
              autoClose: 5000,
              closeButton: true,
            });
          }
        };

        // Fetch once immediately, then poll often enough to expose real node
        // and section milestones without creating excessive API traffic.
        await pollPreviewStatus();
        if (!pollingFinished) {
          pollInterval = setInterval(pollPreviewStatus, 4000);
        }

        // Keep polling for long source-backed generations for up to ten minutes.
        // The completed result remains recoverable from the server afterwards.
        if (!pollingFinished) {
          safetyTimeout = setTimeout(() => {
            stopPolling();
            toast.update(currentProgressToast, {
              render: 'Preview is still processing. Reopen this page later to retrieve it.',
              type: 'warning',
              isLoading: false,
              autoClose: 5000,
              closeButton: true,
            });
          }, 600000); // 10-minute safety window
        }

      } else {
        releaseGenerationLock();
        console.error('Preview API failed:', response);
        toast.update(toastId, {
          render: response.error || response.message || 'Failed to generate preview',
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
      }
    } catch (error) {
      releaseGenerationLock();
      console.error('Preview error:', error);
      toast.update(toastId, {
        render: error instanceof Error ? error.message : 'Failed to generate preview',
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

    if (!acquireGenerationLock()) {
      console.log('Already finalizing, skipping duplicate call');
      return;
    }

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
          render: 'SOW finalized and saved successfully!',
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
      releaseGenerationLock();
    }
  };

  const handleEditFromPreview = () => {
    const previewId = previewData?.preview_id || localStorage.getItem('lastPreviewId');

    if (!previewId) {
      toast.error('No preview ID found');
      return;
    }

    const content = getEffectivePreviewContent(previewData);
    if (!content || typeof content !== 'object' || Array.isArray(content)) {
      toast.error('This preview does not contain editable document content');
      return;
    }

    const editable = serializePreviewContent(content as Record<string, unknown>);
    if (editable.sections.length === 0) {
      toast.error('No editable Markdown sections were found in this preview');
      return;
    }

    setEditData(previewData);
    setMarkdownDraft(editable.markdown);
    setEditableMarkdownSections(editable.sections);
    setShowPreviewModal(false);
    setShowEditModal(true);
  };

  const handleCloseEditor = () => {
    setShowEditModal(false);
    setShowPreviewModal(true);
  };

  const handleReviewPreview = () => {
    if (!previewData) {
      toast.error('The generated preview is no longer available');
      return;
    }
    setShowPreviewModal(true);
  };

  const handleRecalculatePricing = async () => {
    const previewId = previewData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) return;
    setIsRecalculatingPricing(true);
    try {
      const response = await apiService.recalculateAwsPricing(previewId, {
        region: formData.pricingRegion,
        includeProposed: formData.pricingIncludeProposed,
      });
      if (!response.success) throw new Error(response.error || 'AWS pricing recalculation failed');
      setPreviewData(response);
      toast.success('AWS pricing recalculated');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'AWS pricing recalculation failed');
    } finally {
      setIsRecalculatingPricing(false);
    }
  };

  const renderPreviewSection = (section: string, content: unknown) => {
    if (!isPreviewBodyKey(section) && !section.startsWith('architecture_diagram_asset')) {
      return null;
    }
    const isEdited = previewData.edited_sections && previewData.edited_sections.includes(section);
    if (
      (section === 'architecture_diagram_assets' && Array.isArray(content)) ||
      (section === 'architecture_diagram_asset' && content && typeof content === 'object')
    ) {
      const assets = Array.isArray(content)
        ? content as ArchitectureDiagramAsset[]
        : [content as ArchitectureDiagramAsset];
      return (
        <div key={section} className="preview-content-section architecture-diagram-preview">
          <div className="preview-content-section-title">
            <h4>Architecture Diagrams</h4>
          </div>
          {assets.map((asset, index) => (
            <div className="architecture-diagram-item" key={`${asset.diagram_type || asset.title}-${index}`}>
              <img src={`data:image/png;base64,${asset.image_base64}`} alt={asset.alt_text || asset.title} />
              {asset.caption && <p className="architecture-diagram-caption">Figure {index + 1}: {asset.caption}</p>}
              <div className="architecture-diagram-actions">
                <button className="modal-btn modal-btn-primary" onClick={() => setDiagramEditorAsset({ asset, index })}>
                  <Edit size={15} /> Edit Diagram
                </button>
                <a className="modal-btn modal-btn-secondary" href={asset.edit_url} target="_blank" rel="noreferrer">
                  Open in draw.io
                </a>
              </div>
            </div>
          ))}
        </div>
      );
    }
    return (
      <div
        key={section}
        id={`section-${section}`}
        className={`preview-content-section ${isEdited ? 'edited-section' : ''}`}
      >
        <div className="preview-content-section-title">
          <h4>{previewSectionLabel(section)}</h4>
          {isEdited && <span className="edited-badge">Edited</span>}
        </div>
        <MarkdownRenderer markdown={String(content ?? '')} />
      </div>
    );
  };

  const handleSaveEdit = async () => {
    if (!markdownDraft.trim()) {
      toast.error('The Markdown document cannot be empty');
      return;
    }

    const previewId = editData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) {
      toast.error('No preview ID found');
      return;
    }

    let parsedContent: Record<string, string>;
    try {
      parsedContent = parsePreviewContentMarkdown(markdownDraft, editableMarkdownSections);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to read the Markdown section headings');
      return;
    }

    const toastId = toast.loading('Saving Markdown changes...', {
      position: 'top-right',
      autoClose: false,
    });
    setIsSavingMarkdown(true);

    try {
      const response = await apiService.updatePreviewContent(previewId, parsedContent);

      console.log('Save Edit Response:', response);

      if (response.success) {
        toast.update(toastId, {
          render: 'Markdown changes saved to the preview',
          type: 'success',
          isLoading: false,
          autoClose: 3000,
          closeButton: true,
        });

        setShowEditModal(false);
        setPreviewData(response);
        setShowPreviewModal(true);
        setMarkdownDraft('');
        setEditableMarkdownSections([]);
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
    } finally {
      setIsSavingMarkdown(false);
    }
  };

  const isFormComplete = isFormValid();
  const effectivePreviewContent = getEffectivePreviewContent(previewData);

  return (
    <div className="sow-generator-container">
      <div className="form-header">
        <div className="header-info">
          <h1 className="form-title">Create Statement of Work</h1>
          <p className="form-description">Fill in the details below to generate your professional SOW document</p>
        </div>
      </div>

      <div className="form-content">
        <div className="section-group bu-assignment-section">
          <div className="section-header">
            <h2 className="section-title">Business Unit</h2>
          </div>
          <div className="field-group">
            <label htmlFor="businessUnit" className="field-label">
              SOW Owner <span className="required">*</span>
            </label>
            {canSelectBusinessUnit ? (
              <select
                id="businessUnit"
                name="businessUnit"
                value={formData.businessUnit || ''}
                onChange={handleInputChange}
                className="field-input"
              >
                <option value="">Select business unit...</option>
                {selectableBusinessUnits.map(unit => <option key={unit} value={unit}>{unit}</option>)}
              </select>
            ) : (
              <input className="field-input auto-populated" value={user?.business_unit || ''} readOnly />
            )}
          </div>
        </div>
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
                    <span className="upload-hint">Only PDF, Word (DOC/DOCX), Excel (XLS/XLSX), and TXT files are supported • Max 10MB per file</span>
                  </div>
                  <input
                    id="file-input"
                    type="file"
                    multiple
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
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
              {hasPreviewGenerated && previewData && (
                <button type="button" onClick={handleReviewPreview} className="review-preview-button">
                  <Eye className="button-icon" />
                  <span className="button-text">Review Preview</span>
                </button>
              )}
              <button
                onClick={hasPreviewGenerated ? handleGenerateSOW : handlePreview}
                disabled={isGenerating}
                aria-disabled={!isFormComplete || isGenerating}
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
                      Crafting Your Document...
                    </span>
                  </>
                ) : (
                  <>
                    <Wand2 className="button-icon" />
                    <span className="button-text">
                      {hasPreviewGenerated ? 'Finalize & Deliver' : 'Craft SOW Document'}
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

              {selectedSowSections.includes('aws_pricing') && (
                <div className="pricing-options-panel" style={{ marginTop: '20px', padding: '18px', border: '1px solid #dbe4f0', borderRadius: '12px', background: '#f8fafc' }}>
                  <h3 style={{ margin: '0 0 6px', fontSize: '16px' }}>AWS Pricing Calculator</h3>
                  <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: '13px' }}>
                    A calculator estimate is created only from usage values found in the uploaded documents or additional details. Missing sizing inputs remain open for confirmation.
                  </p>
                  <div className="field-group" style={{ marginBottom: '12px' }}>
                    <label htmlFor="pricingRegion" className="field-label">AWS Region</label>
                    <input
                      id="pricingRegion"
                      className="field-input"
                      list="aws-region-options"
                      placeholder="Extract from source, or enter a region code"
                      value={formData.pricingRegion || ''}
                      onChange={(event) => setFormData(previous => ({ ...previous, pricingRegion: event.target.value }))}
                    />
                    <datalist id="aws-region-options">
                      <option value="ap-south-1">Asia Pacific (Mumbai)</option>
                      <option value="ap-south-2">Asia Pacific (Hyderabad)</option>
                      <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                      <option value="us-east-1">US East (N. Virginia)</option>
                      <option value="us-west-2">US West (Oregon)</option>
                      <option value="eu-west-1">Europe (Ireland)</option>
                    </datalist>
                  </div>
                  <label style={{ display: 'flex', gap: '9px', alignItems: 'flex-start', marginBottom: '10px', fontSize: '13px' }}>
                    <input
                      type="checkbox"
                      checked={formData.pricingIncludeProposed ?? true}
                      onChange={(event) => setFormData(previous => ({ ...previous, pricingIncludeProposed: event.target.checked }))}
                    />
                    Price architect-recommended AWS services as well as services explicitly named in the source, but only when the source provides their usage sizing
                  </label>
                </div>
              )}
              
              {/* Supporting documents are the primary requirements source. */}
              <div className="field-group full-width" style={{ marginTop: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <Upload className="section-icon" style={{ width: '20px', height: '20px' }} />
                  <label className="field-label" style={{ marginBottom: 0 }}>Business Requirements Document (BRD) or Supporting Document</label>
                </div>
                <p style={{ fontSize: '14px', color: '#666', marginBottom: '12px', marginTop: '4px' }}>
                  Uploads are treated as the primary requirements source. Add optional generation guidance below to refine scope, priorities, or treatment of specific capabilities.
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
                      <span className="upload-hint">Only PDF, Word (DOC/DOCX), Excel (XLS/XLSX), and TXT files are supported • Max 10MB per file</span>
                    </div>
                    <input
                      id="file-input-support"
                      type="file"
                      multiple
                      accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
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

              {/* Guidance influences the full document without replacing uploaded evidence. */}
              <div className="field-group full-width" style={{ marginTop: '24px' }}>
                <label htmlFor="projectObjective" className="field-label">
                  Additional Details &amp; Generation Guidance
                </label>
                <p style={{ fontSize: '14px', color: '#666', marginBottom: '10px', marginTop: '4px' }}>
                  Use this to guide the AI across the SOW—for example, prioritise selected deliverables or move a capability to future scope. If no document is uploaded, these details become the primary project source.
                </p>
                <textarea
                  id="projectObjective"
                  name="projectObjective"
                  value={formData.projectObjective}
                  onChange={handleInputChange}
                  placeholder="Example: Treat voice capability as future scope, and make workflow automation the primary deliverable..."
                  className="field-textarea"
                  rows={5}
                  style={{
                    height: '120px',
                    minHeight: '120px',
                    maxHeight: '120px',
                    resize: 'none'
                  }}
                />
              </div>
            </div>

            {/* Smart Single Button for POC/PROD */}
            <div className="button-container" style={{ marginTop: '24px' }}>
              {hasPreviewGenerated && previewData && (
                <button type="button" onClick={handleReviewPreview} className="review-preview-button">
                  <Eye className="button-icon" />
                  <span className="button-text">Review Preview</span>
                </button>
              )}
              <button
                onClick={hasPreviewGenerated ? handleGenerateSOW : handlePreview}
                disabled={isGenerating}
                aria-disabled={!isFormComplete || isGenerating}
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
                    ? 'Complete the required fields and provide a supporting document or sufficient additional details'
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
                      Crafting Your Document...
                    </span>
                  </>
                ) : (
                  <>
                    <Wand2 className="button-icon" />
                    <span className="button-text">
                      {hasPreviewGenerated ? 'Finalize & Deliver' : 'Craft SOW Document'}
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

              {previewData.pricing_result && previewData.pricing_result.status !== 'not_selected' && (
                <div className="preview-status-card" style={{ marginTop: '18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center' }}>
                    <div>
                      <strong>AWS Pricing Calculator</strong>
                      <div style={{ marginTop: '4px', color: '#64748b', fontSize: '13px' }}>
                        Status: {String(previewData.pricing_result.status).replace(/_/g, ' ')}
                        {previewData.pricing_result.region ? ` • ${previewData.pricing_result.region}` : ''}
                        {previewData.pricing_result.monthly_cost != null ? ` • USD ${Number(previewData.pricing_result.monthly_cost).toFixed(2)}/month` : ''}
                      </div>
                      {previewData.pricing_result.estimate_url && (
                        <a href={previewData.pricing_result.estimate_url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: '6px' }}>
                          Open editable calculator estimate
                        </a>
                      )}
                      {(previewData.pricing_result.missing_inputs?.length > 0 || previewData.pricing_result.stale) && (
                        <div style={{ marginTop: '6px', color: '#b45309', fontSize: '13px' }}>
                          {previewData.pricing_result.stale
                            ? 'Pricing-relevant content changed; recalculate before finalising.'
                            : `${previewData.pricing_result.missing_inputs.length} pricing input(s) require confirmation.`}
                        </div>
                      )}
                    </div>
                    <button className="modal-btn modal-btn-secondary" onClick={handleRecalculatePricing} disabled={isRecalculatingPricing}>
                      {isRecalculatingPricing ? 'Recalculating...' : 'Recalculate'}
                    </button>
                  </div>
                </div>
              )}

              {/* Display the latest preview content once, with Markdown formatting. */}
              {effectivePreviewContent && (
                typeof effectivePreviewContent === 'string'
                  ? effectivePreviewContent.length > 0
                  : Object.keys(effectivePreviewContent as object).length > 0
              ) && (
                <>
                  <h3 className="preview-section-title">Document Sections</h3>
                  <div className="preview-content-display">
                    {typeof effectivePreviewContent === 'string' ? (
                      <div className="preview-content-section">
                        <MarkdownRenderer markdown={effectivePreviewContent} />
                      </div>
                    ) : (
                      <div className="preview-content-sections">
                        {Object.entries(effectivePreviewContent as Record<string, unknown>)
                          .map(([section, content]) => renderPreviewSection(section, content))}
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Show empty-content diagnostic if the latest content block has no data. */}
              {(!effectivePreviewContent || Object.keys(effectivePreviewContent || {}).length === 0) &&
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

      {diagramEditorAsset && previewData?.preview_id && (
        <DiagramEditorModal
          previewId={previewData.preview_id}
          asset={diagramEditorAsset.asset}
          diagramIndex={diagramEditorAsset.index}
          onClose={() => setDiagramEditorAsset(null)}
          onSaved={(asset) => {
            const savedIndex = diagramEditorAsset.index;
            setDiagramEditorAsset({ asset, index: savedIndex });
            const updateDiagramContent = (content: any) => {
              if (!content) return content;
              if (Array.isArray(content.architecture_diagram_assets)) {
                const assets = [...content.architecture_diagram_assets];
                assets[savedIndex] = asset;
                return { ...content, architecture_diagram_assets: assets };
              }
              if (content.architecture_diagram_asset) {
                return { ...content, architecture_diagram_asset: asset };
              }
              return content;
            };
            setPreviewData((current: any) => ({
              ...current,
              content: updateDiagramContent(current?.content),
              updated_content: updateDiagramContent(current?.updated_content),
            }));
            toast.success('Architecture diagram saved to the preview.');
          }}
        />
      )}

      {/* Direct Markdown editor — uses the generated preview content itself. */}
      {showEditModal && editData && ReactDOM.createPortal(
        <div className="modal-overlay" onClick={handleCloseEditor}>
          <div className="modal-content modal-large markdown-edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>Edit SOW Markdown</h2>
                <p className="markdown-editor-subtitle">Edit the complete generated body in one place. The front page, table of contents, page numbers, and diagram assets remain managed automatically.</p>
              </div>
              <button className="modal-close" onClick={handleCloseEditor}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body markdown-edit-body">
              <div className="markdown-editor-notice">
                Keep each <code>## Section Heading</code> line in place. Use <code>###</code> for any new subtopics. Markdown tables, lists, emphasis, links, and headings are rendered in the preview beside the editor.
              </div>
              <div className="markdown-editor-layout">
                <div className="markdown-editor-pane">
                  <label htmlFor="sow-markdown-editor">Markdown</label>
                  <textarea
                    id="sow-markdown-editor"
                    className="markdown-document-editor"
                    value={markdownDraft}
                    onChange={(event) => setMarkdownDraft(event.target.value)}
                    spellCheck
                    aria-describedby="sow-markdown-help"
                  />
                  <span id="sow-markdown-help" className="markdown-editor-meta">
                    {editableMarkdownSections.length} sections · {markdownDraft.length.toLocaleString()} characters
                  </span>
                </div>
                <div className="markdown-editor-pane markdown-live-preview-pane">
                  <div className="markdown-live-preview-title">Live preview</div>
                  <div className="markdown-live-preview">
                    <MarkdownRenderer markdown={markdownDraft} />
                  </div>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={handleCloseEditor}>
                Close
              </button>
              <button 
                className="modal-btn modal-btn-primary" 
                onClick={handleSaveEdit}
                disabled={!markdownDraft.trim() || isSavingMarkdown}
              >
                {isSavingMarkdown ? <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} /> : <Edit size={16} style={{ marginRight: '8px' }} />}
                {isSavingMarkdown ? 'Saving...' : 'Save Markdown'}
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
