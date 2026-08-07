import React, { useState, useEffect } from 'react';
import { Upload, FileText, Zap, Clock, CheckCircle, AlertCircle, FolderOpen, Download, ExternalLink, X } from 'lucide-react';

const SOWGeneratorUI = () => {
  const [mode, setMode] = useState('');
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    companyName: '',
    authorName: '',
    authorOrg: '',
    documentDate: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
    version: '1.0',
    objective: '',
    sourceFile: null,
    uploadToDrive: false
  });
  const [recentDocs, setRecentDocs] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationComplete, setGenerationComplete] = useState(false);
  const [generatedFile, setGeneratedFile] = useState(null);
  const [error, setError] = useState(null);
  const [uploadedFilePath, setUploadedFilePath] = useState(null);

  const API_BASE = 'http://localhost:5000/api';

  // Mock recent documents for demonstration
  useEffect(() => {
    setRecentDocs([
      { id: 1, name: 'SOW_Acme_Corp_POC.docx', date: '29 Dec 2025', mode: 'POC' },
      { id: 2, name: 'SOW_TechFlow_Production.docx', date: '28 Dec 2025', mode: 'PROD' },
      { id: 3, name: 'SOW_CloudStart_Converted.docx', date: '27 Dec 2025', mode: 'PROD' }
    ]);
  }, []);

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!validTypes.includes(file.type)) {
      setError('Please upload a PDF or DOCX file');
      return;
    }

    setError(null);
    setFormData(prev => ({ ...prev, sourceFile: file }));
    setUploadedFilePath(file.name);
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);

    // Simulate document generation
    await new Promise(resolve => setTimeout(resolve, 2000));

    setGeneratedFile({
      name: `SOW_${formData.companyName.replace(/\s+/g, '_')}_${new Date().getTime()}.docx`,
      path: `/output/Production/SOW_Document.docx`,
      driveLink: null,
      driveUploaded: false
    });
    setGenerationComplete(true);
    setIsGenerating(false);
  };

  const handleDownload = () => {
    if (generatedFile?.name) {
      // In a real application, this would trigger the actual download
      alert(`Downloading: ${generatedFile.name}`);
    }
  };

  const resetForm = () => {
    setMode('');
    setStep(1);
    setFormData({
      companyName: '',
      authorName: '',
      authorOrg: '',
      documentDate: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
      version: '1.0',
      objective: '',
      sourceFile: null,
      uploadToDrive: false
    });
    setGenerationComplete(false);
    setGeneratedFile(null);
    setError(null);
    setUploadedFilePath(null);
  };

  const ModeCard = ({ icon: Icon, title, description, value, gradient }) => (
    <div
      onClick={() => {
        setMode(value);
        setStep(2);
        setError(null);
      }}
      className={`cursor-pointer p-6 rounded-xl border-2 transition-all duration-300 hover:scale-105 ${
        mode === value 
          ? `border-purple-500 bg-gradient-to-br ${gradient}` 
          : 'border-gray-200 hover:border-purple-300 bg-white'
      }`}
    >
      <Icon className={`w-12 h-12 mb-4 ${mode === value ? 'text-white' : 'text-purple-500'}`} />
      <h3 className={`text-xl font-bold mb-2 ${mode === value ? 'text-white' : 'text-gray-800'}`}>
        {title}
      </h3>
      <p className={`text-sm ${mode === value ? 'text-purple-100' : 'text-gray-600'}`}>
        {description}
      </p>
    </div>
  );

  const HistoryItem = ({ doc }) => (
    <div className="p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer border border-gray-200">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <FileText className="w-4 h-4 text-purple-500" />
            <span className="font-semibold text-sm text-gray-800">{doc.name}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {doc.date}
            </span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              doc.mode === 'POC' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
            }`}>
              {doc.mode}
            </span>
          </div>
        </div>
        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
      </div>
    </div>
  );

  const isFormValid = () => {
    if (mode === 'POC_TO_PROD') {
      return formData.sourceFile !== null;
    }
    return formData.companyName && formData.authorName && formData.authorOrg && formData.objective;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-blue-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-purple-700 rounded-xl flex items-center justify-center shadow-lg">
              <FileText className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
              AWS SOW Generator
            </h1>
          </div>
          <p className="text-gray-600 text-lg">LangGraph Edition - Automated Document Creation</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Main Content */}
          <div className="lg:col-span-3">
            <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
              
              {/* Error Message */}
              {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-red-800 font-medium">Error</p>
                    <p className="text-red-600 text-sm">{error}</p>
                  </div>
                  <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              )}

              {/* Step 1: Mode Selection */}
              {step === 1 && (
                <div className="space-y-6">
                  <h2 className="text-2xl font-bold text-gray-800 mb-6">Select Generation Mode</h2>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <ModeCard
                      icon={Zap}
                      title="SOW for POC"
                      description="Generate Statement of Work for Proof of Concept projects"
                      value="POC"
                      gradient="from-purple-500 to-purple-700"
                    />
                    
                    <ModeCard
                      icon={FileText}
                      title="SOW for Production"
                      description="Create comprehensive production-ready SOW documents"
                      value="PROD"
                      gradient="from-blue-500 to-blue-700"
                    />
                    
                    <ModeCard
                      icon={Upload}
                      title="POC to Production"
                      description="Convert existing POC document to production format"
                      value="POC_TO_PROD"
                      gradient="from-green-500 to-green-700"
                    />
                  </div>
                </div>
              )}

              {/* Step 2: Form Input */}
              {step === 2 && !generationComplete && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-gray-800">
                      {mode === 'POC' && 'POC Document Details'}
                      {mode === 'PROD' && 'Production Document Details'}
                      {mode === 'POC_TO_PROD' && 'Upload Existing POC'}
                    </h2>
                    <button
                      onClick={() => {
                        setStep(1);
                        setError(null);
                      }}
                      className="text-purple-600 hover:text-purple-800 font-medium"
                    >
                      ← Change Mode
                    </button>
                  </div>

                  {mode === 'POC_TO_PROD' ? (
                    <div className="space-y-6">
                      <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-purple-400 transition-colors">
                        <Upload className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                        <label className="cursor-pointer">
                          <div>
                            <span className="text-lg font-semibold text-gray-700 block mb-2">
                              {formData.sourceFile ? (
                                <span className="text-green-600 flex items-center justify-center gap-2">
                                  <CheckCircle className="w-5 h-5" />
                                  {formData.sourceFile.name}
                                </span>
                              ) : (
                                'Click to Browse and Upload POC Document'
                              )}
                            </span>
                            <span className="text-sm text-gray-500">
                              PDF or DOCX files only
                            </span>
                          </div>
                          <input
                            type="file"
                            accept=".pdf,.docx"
                            onChange={handleFileSelect}
                            className="hidden"
                          />
                        </label>
                      </div>

                      {formData.sourceFile && (
                        <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                          <div className="flex items-center gap-2 text-green-700">
                            <CheckCircle className="w-5 h-5" />
                            <span className="font-medium">File uploaded successfully</span>
                          </div>
                          <p className="text-sm text-green-600 mt-1">
                            Ready to convert to Production SOW
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Company Name *
                          </label>
                          <input
                            type="text"
                            name="companyName"
                            value={formData.companyName}
                            onChange={handleInputChange}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                            placeholder="Enter company name"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Author Name *
                          </label>
                          <input
                            type="text"
                            name="authorName"
                            value={formData.authorName}
                            onChange={handleInputChange}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                            placeholder="Your name"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Author Organization *
                          </label>
                          <input
                            type="text"
                            name="authorOrg"
                            value={formData.authorOrg}
                            onChange={handleInputChange}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                            placeholder="Your organization"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Document Date
                          </label>
                          <input
                            type="text"
                            name="documentDate"
                            value={formData.documentDate}
                            onChange={handleInputChange}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Version
                          </label>
                          <input
                            type="text"
                            name="version"
                            value={formData.version}
                            onChange={handleInputChange}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                          Project Objective *
                        </label>
                        <textarea
                          name="objective"
                          value={formData.objective}
                          onChange={handleInputChange}
                          rows={4}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          placeholder="Describe the project objective and scope..."
                        />
                      </div>
                    </div>
                  )}

                  <div className="flex items-center gap-3 p-4 bg-purple-50 rounded-lg border border-purple-200">
                    <input
                      type="checkbox"
                      name="uploadToDrive"
                      checked={formData.uploadToDrive}
                      onChange={handleInputChange}
                      className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500"
                    />
                    <label className="text-sm font-medium text-gray-700">
                      Upload final document to Google Drive
                    </label>
                  </div>

                  {isGenerating ? (
                    <div className="text-center py-8">
                      <div className="inline-block w-16 h-16 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-4" />
                      <p className="text-lg font-semibold text-gray-700">
                        {mode === 'POC_TO_PROD' && formData.sourceFile && !uploadedFilePath
                          ? 'Uploading file...'
                          : 'Generating your document...'}
                      </p>
                      <p className="text-sm text-gray-500 mt-2">This may take a few moments</p>
                    </div>
                  ) : (
                    <button
                      onClick={handleGenerate}
                      disabled={!isFormValid()}
                      className="w-full bg-gradient-to-r from-purple-600 to-purple-700 text-white font-semibold py-4 rounded-xl hover:from-purple-700 hover:to-purple-800 transition-all duration-300 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      <Zap className="w-5 h-5" />
                      {mode === 'POC_TO_PROD' ? 'Convert to Production' : 'Generate Document'}
                    </button>
                  )}
                </div>
              )}

              {/* Step 3: Success */}
              {generationComplete && (
                <div className="text-center py-8">
                  <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <CheckCircle className="w-12 h-12 text-green-500" />
                  </div>
                  
                  <h2 className="text-3xl font-bold text-gray-800 mb-2">Document Generated!</h2>
                  <p className="text-gray-600 mb-8">Your SOW document is ready</p>

                  <div className="bg-gray-50 rounded-xl p-6 mb-6 border border-gray-200">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <FileText className="w-6 h-6 text-purple-600" />
                        <div className="text-left">
                          <p className="font-semibold text-gray-800">{generatedFile?.name}</p>
                          <p className="text-sm text-gray-500">Saved locally</p>
                        </div>
                      </div>
                      <button
                        onClick={handleDownload}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors flex items-center gap-2"
                      >
                        <Download className="w-4 h-4" />
                        Download
                      </button>
                    </div>

                    {generatedFile?.driveUploaded && generatedFile?.driveLink && (
                      <a
                        href={generatedFile.driveLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 text-purple-600 hover:text-purple-800 font-medium py-2 px-4 bg-purple-50 rounded-lg hover:bg-purple-100 transition-colors"
                      >
                        <ExternalLink className="w-4 h-4" />
                        View in Google Drive
                      </a>
                    )}

                    {formData.uploadToDrive && !generatedFile?.driveUploaded && (
                      <div className="flex items-center justify-center gap-2 text-amber-600 py-2 px-4 bg-amber-50 rounded-lg">
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-sm">Drive upload was not successful</span>
                      </div>
                    )}
                  </div>

                  <button
                    onClick={resetForm}
                    className="bg-gradient-to-r from-purple-600 to-purple-700 text-white font-semibold px-8 py-3 rounded-xl hover:from-purple-700 hover:to-purple-800 transition-all duration-300 shadow-lg"
                  >
                    Generate Another Document
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Sidebar - Recent Documents */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-2xl shadow-xl p-6 border border-gray-100 sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                  <FolderOpen className="w-5 h-5 text-purple-600" />
                  Recent Documents
                </h3>
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                {recentDocs.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No documents yet</p>
                  </div>
                ) : (
                  recentDocs.map(doc => <HistoryItem key={doc.id} doc={doc} />)
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SOWGeneratorUI;