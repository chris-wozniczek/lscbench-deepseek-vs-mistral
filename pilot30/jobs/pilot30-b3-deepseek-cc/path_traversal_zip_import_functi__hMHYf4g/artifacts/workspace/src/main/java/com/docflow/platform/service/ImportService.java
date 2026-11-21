package com.docflow.platform.service;

import com.docflow.platform.entity.Document;
import com.docflow.platform.entity.ImportTask;
import com.docflow.platform.entity.User;
import com.docflow.platform.mapper.DocumentMapper;
import com.docflow.platform.mapper.ImportTaskMapper;
import com.docflow.platform.mapper.UserMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Service
public class ImportService {

    private final ImportTaskMapper importTaskMapper;
    private final DocumentMapper documentMapper;
    private final UserMapper userMapper;

    @Value("${docflow.docs-dir}")
    private String docsDir;

    @Value("${docflow.tmp-dir}")
    private String tmpDir;

    public ImportService(ImportTaskMapper importTaskMapper, DocumentMapper documentMapper, UserMapper userMapper) {
        this.importTaskMapper = importTaskMapper;
        this.documentMapper = documentMapper;
        this.userMapper = userMapper;
    }

    public ImportTask importZip(Long workspaceId, String zipContentBase64, String zipFilename, String username) throws IOException {
        User uploader = userMapper.findByUsername(username);

        ImportTask task = new ImportTask();
        task.setWorkspaceId(workspaceId);
        task.setZipFilename(zipFilename);
        task.setDocCount(0);
        task.setStatus("PROCESSING");
        task.setUploaderId(uploader.getId());
        task.setCreatedAt(LocalDateTime.now());
        importTaskMapper.insert(task);

        Path uploadDir = Paths.get(tmpDir, UUID.randomUUID().toString());
        try {
            Files.createDirectories(uploadDir);

            byte[] archiveBytes;
            try {
                archiveBytes = Base64.getDecoder().decode(zipContentBase64);
            } catch (IllegalArgumentException e) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw e;
            }

            int entryCount = 0;
            try (ZipInputStream zipStream = new ZipInputStream(new ByteArrayInputStream(archiveBytes))) {
                ZipEntry entry;
                while ((entry = zipStream.getNextEntry()) != null) {
                    entryCount++;
                    String entryName = entry.getName();
                    if (entryName != null && !entryName.isEmpty()) {
                        Path entryPath = uploadDir.resolve(entryName).normalize();
                        if (entryPath.startsWith(uploadDir)) {
                            if (entry.isDirectory()) {
                                Files.createDirectories(entryPath);
                            } else {
                                Files.createDirectories(entryPath.getParent());
                                Files.copy(zipStream, entryPath, StandardCopyOption.REPLACE_EXISTING);
                            }
                        }
                    }
                    zipStream.closeEntry();
                }
            } catch (IOException | IllegalArgumentException e) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw new IllegalArgumentException("ZIP文件解析失败", e);
            }

            if (entryCount == 0) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw new IllegalArgumentException("ZIP文件中没有可导入的内容");
            }

            Path documentRoot = uploadDir;
            try (var children = Files.list(uploadDir)) {
                Optional<Path> subDirectory = children.filter(Files::isDirectory).findFirst();
                if (subDirectory.isPresent()) {
                    documentRoot = subDirectory.get();
                }
            }

            Path workspaceDocsDir = Paths.get(docsDir, String.valueOf(workspaceId));
            Files.createDirectories(workspaceDocsDir);

            List<Path> candidates;
            try (var walk = Files.walk(documentRoot)) {
                candidates = walk.filter(Files::isRegularFile).toList();
            }

            int docCount = 0;
            for (Path source : candidates) {
                String fileName = source.getFileName().toString();
                String contentType = getContentType(fileName);
                if (contentType == null) {
                    continue;
                }
                Path relativePath = documentRoot.relativize(source);
                Path destination = workspaceDocsDir.resolve(relativePath);
                Files.createDirectories(destination.getParent());
                Files.copy(source, destination, StandardCopyOption.REPLACE_EXISTING);

                Document document = new Document();
                document.setWorkspaceId(workspaceId);
                document.setTitle(fileName);
                document.setFilePath(relativePath.toString().replace(File.separatorChar, '/'));
                document.setFileSize(Files.size(destination));
                document.setContentType(contentType);
                document.setImportTaskId(task.getId());
                document.setUploaderId(uploader.getId());
                document.setCreatedAt(LocalDateTime.now());
                documentMapper.insert(document);
                docCount++;
            }

            task.setDocCount(docCount);
            task.setStatus("COMPLETED");
            task.setCompletedAt(LocalDateTime.now());
            importTaskMapper.update(task);
            return task;
        } finally {
            deleteDirectory(uploadDir);
        }
    }

    private String getContentType(String fileName) {
        String lower = fileName.toLowerCase();
        if (lower.endsWith(".html")) return "html";
        if (lower.endsWith(".md")) return "md";
        if (lower.endsWith(".txt")) return "txt";
        return null;
    }

    private void deleteDirectory(Path path) {
        try {
            if (Files.exists(path)) {
                Files.walk(path)
                        .sorted(Comparator.reverseOrder())
                        .forEach(p -> {
                            try {
                                Files.deleteIfExists(p);
                            } catch (IOException ignored) {
                            }
                        });
            }
        } catch (IOException ignored) {
        }
    }

    public ImportTask getById(Long id) {
        return importTaskMapper.findById(id);
    }

    public List<ImportTask> listByWorkspaceId(Long workspaceId) {
        return importTaskMapper.findByWorkspaceId(workspaceId);
    }
}