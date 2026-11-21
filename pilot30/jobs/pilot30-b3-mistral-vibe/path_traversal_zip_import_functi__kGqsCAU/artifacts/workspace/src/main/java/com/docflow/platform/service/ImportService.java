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
        Long uploaderId = uploader.getId();

        ImportTask task = new ImportTask();
        task.setWorkspaceId(workspaceId);
        task.setZipFilename(zipFilename);
        task.setDocCount(0);
        task.setStatus("PROCESSING");
        task.setUploaderId(uploaderId);
        task.setCreatedAt(LocalDateTime.now());
        importTaskMapper.insert(task);

        Path uploadDir = Paths.get(tmpDir, UUID.randomUUID().toString());
        Files.createDirectories(uploadDir);
        try {
            byte[] zipBytes;
            try {
                zipBytes = Base64.getDecoder().decode(zipContentBase64);
            } catch (IllegalArgumentException e) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw e;
            }

            int entryCount = 0;
            try (ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(zipBytes))) {
                ZipEntry entry;
                while ((entry = zis.getNextEntry()) != null) {
                    entryCount++;
                    Path target = uploadDir.resolve(entry.getName()).normalize();
                    if (!target.startsWith(uploadDir)) {
                        throw new IOException("ZIP entry escapes upload directory: " + entry.getName());
                    }
                    if (entry.isDirectory()) {
                        Files.createDirectories(target);
                    } else {
                        if (target.getParent() != null) {
                            Files.createDirectories(target.getParent());
                        }
                        Files.copy(zis, target, StandardCopyOption.REPLACE_EXISTING);
                    }
                    zis.closeEntry();
                }
            } catch (java.util.zip.ZipException e) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw new IllegalArgumentException("Invalid ZIP archive", e);
            }

            if (entryCount == 0) {
                task.setStatus("FAILED");
                task.setCompletedAt(LocalDateTime.now());
                importTaskMapper.update(task);
                throw new IllegalArgumentException("ZIP archive contains no entries");
            }

            Path documentRoot = uploadDir;
            try (var stream = Files.list(uploadDir)) {
                documentRoot = stream.filter(Files::isDirectory)
                        .sorted()
                        .findFirst()
                        .orElse(uploadDir);
            }

            Path workspaceDocsDir = Paths.get(docsDir, String.valueOf(workspaceId));
            Files.createDirectories(workspaceDocsDir);

            List<Path> selected = new ArrayList<>();
            try (var walk = Files.walk(documentRoot)) {
                walk.filter(Files::isRegularFile)
                        .filter(p -> getContentType(p.getFileName().toString()) != null)
                        .forEach(selected::add);
            }
            selected.sort(Comparator.naturalOrder());

            for (Path file : selected) {
                String relative = documentRoot.relativize(file).toString();
                Path target = workspaceDocsDir.resolve(relative).normalize();
                if (target.getParent() != null) {
                    Files.createDirectories(target.getParent());
                }
                Files.copy(file, target, StandardCopyOption.REPLACE_EXISTING);

                Document document = new Document();
                document.setWorkspaceId(workspaceId);
                document.setTitle(file.getFileName().toString());
                document.setFilePath(relative);
                document.setFileSize(Files.size(target));
                document.setContentType(getContentType(file.getFileName().toString()));
                document.setImportTaskId(task.getId());
                document.setUploaderId(uploaderId);
                document.setCreatedAt(LocalDateTime.now());
                documentMapper.insert(document);
            }

            task.setDocCount(selected.size());
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