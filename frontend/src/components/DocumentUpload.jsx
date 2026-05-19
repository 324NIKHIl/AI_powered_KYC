import { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'

const ALLOWED = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'application/pdf': ['.pdf'],
}

const MAX_SIZE = 10 * 1024 * 1024 // 10 MB

export default function DocumentUpload({
  onFileSelected,
  uploading,
  uploadProgress,
}) {
  const [preview, setPreview] = useState(null)
  const [fileInfo, setFileInfo] = useState(null)
  const [error, setError] = useState(null)

  // Cleanup preview URL
  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview)
      }
    }
  }, [preview])

  const onDrop = useCallback(
    (acceptedFiles, rejectedFiles) => {
      setError(null)

      // Handle rejected files
      if (rejectedFiles.length > 0) {
        const err = rejectedFiles[0].errors[0]

        if (err.code === 'file-too-large') {
          setError('File exceeds 10 MB limit')
        } else if (err.code === 'file-invalid-type') {
          setError('Unsupported file type')
        } else {
          setError(err.message)
        }

        return
      }

      // No file selected
      if (!acceptedFiles || acceptedFiles.length === 0) {
        return
      }

      const file = acceptedFiles[0]

      setFileInfo({
        name: file.name,
        size:
          file.size > 1024 * 1024
            ? `${(file.size / (1024 * 1024)).toFixed(2)} MB`
            : `${(file.size / 1024).toFixed(1)} KB`,
      })

      // Cleanup old preview
      if (preview) {
        URL.revokeObjectURL(preview)
      }

      // Generate preview
      if (file.type !== 'application/pdf') {
        const objectUrl = URL.createObjectURL(file)
        setPreview(objectUrl)
      } else {
        setPreview(null)
      }

      // Send file to parent
      onFileSelected(file)
    },
    [onFileSelected, preview]
  )

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    open,
  } = useDropzone({
    onDrop,
    accept: ALLOWED,
    maxFiles: 1,
    maxSize: MAX_SIZE,
    disabled: uploading,
    noClick: true,
    noKeyboard: true,
  })

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={`
          relative border-2 border-dashed rounded-2xl p-8 text-center
          transition-all duration-300 cursor-pointer overflow-hidden
          ${
            isDragActive
              ? 'border-primary bg-primary/5'
              : 'border-white/20 hover:border-primary/50 hover:bg-primary/5'
          }
          ${uploading ? 'opacity-60 cursor-not-allowed' : ''}
        `}
        onClick={() => {
          if (!uploading) {
            open()
          }
        }}
      >
        {/* Hidden File Input */}
        <input
          {...getInputProps()}
          className="hidden"
        />

        <AnimatePresence mode="wait">
          {/* Drag Active */}
          {isDragActive ? (
            <motion.div
              key="drag"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="pointer-events-none"
            >
              <div className="text-5xl mb-3">
                📂
              </div>

              <p className="text-primary font-semibold">
                Drop your document here
              </p>
            </motion.div>
          ) : fileInfo ? (
            /* File Selected */
            <motion.div
              key="file"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="pointer-events-none"
            >
              {preview ? (
                <img
                  src={preview}
                  alt="Document Preview"
                  className="mx-auto max-h-48 rounded-xl object-contain mb-4"
                />
              ) : (
                <div className="text-5xl mb-3">
                  📄
                </div>
              )}

              <p className="text-white font-medium break-all">
                {fileInfo.name}
              </p>

              <p className="text-white/40 text-sm mt-1">
                {fileInfo.size}
              </p>

              {!uploading && (
                <p className="text-primary/70 text-xs mt-3">
                  Click to replace document
                </p>
              )}
            </motion.div>
          ) : (
            /* Empty State */
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="pointer-events-none"
            >
              <div className="text-5xl mb-4 opacity-60">
                🪪
              </div>

              <p className="text-white font-semibold mb-1">
                Upload Identity Document
              </p>

              <p className="text-white/40 text-sm">
                Drag & drop or click to browse
              </p>

              <p className="text-white/30 text-xs mt-3">
                Aadhaar • PAN • Passport • College ID
              </p>

              <p className="text-white/20 text-xs mt-1">
                JPG • PNG • PDF • Max 10 MB
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Upload Progress */}
      {uploading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-1"
        >
          <div className="flex justify-between text-xs text-white/50">
            <span>Uploading & processing...</span>
            <span>{uploadProgress}%</span>
          </div>

          <div className="w-full h-2 bg-surface-600 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-primary to-accent rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${uploadProgress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </motion.div>
      )}

      {/* Error Message */}
      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3"
        >
          <p className="text-red-400 text-sm">
            ⚠ {error}
          </p>
        </motion.div>
      )}
    </div>
  )
}