// components/FileUpload.tsx
import { ChangeEvent, FC, useState } from "react";
import React from "react";
import Dropzone from "react-dropzone";

interface FileUploadProps {
  selectedFiles: File[];
  setSelectedFiles: (files: File[]) => void;
}

export const FileUpload: FC<FileUploadProps> = ({
  selectedFiles,
  setSelectedFiles,
}) => {
  const [dragActive, setDragActive] = useState(false);

  return (
    <div>
      <Dropzone
        onDrop={(acceptedFiles) => {
          setSelectedFiles(acceptedFiles);
          setDragActive(false);
        }}
        onDragLeave={() => setDragActive(false)}
        onDragEnter={() => setDragActive(true)}
      >
        {({ getRootProps, getInputProps }) => (
          <section>
            <div
              {...getRootProps()}
              className={
                "flex flex-col items-center w-full px-4 py-12 rounded " +
                "shadow-lg tracking-wide border border-gray-700 cursor-pointer" +
                (dragActive ? " border-blue-500" : "")
              }
            >
              <input {...getInputProps()} />
              <b>Drag and drop some files here, or click to select files</b>
            </div>
          </section>
        )}
      </Dropzone>

      {selectedFiles.length > 0 && (
        <div className="mt-4">
          <h2 className="font-bold">Selected Files</h2>
          <ul>
            {selectedFiles.map((file) => (
              <div key={file.name} className="flex">
                <p className="text-sm mr-2">{file.name}</p>
              </div>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
