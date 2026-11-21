package com.dochub.platform.service;

import com.dochub.platform.dto.ApiResponse;
import com.dochub.platform.entity.FileRecord;
import com.dochub.platform.mapper.FileMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.*;

@Service
public class FileService {

    @Autowired
    private FileMapper fileMapper;

    public ApiResponse<?> uploadFile(Long docId, MultipartFile file) {
        if (file == null) {
            return ApiResponse.error(400, "请选择文件");
        }

        String originalName = file.getOriginalFilename();
        if (originalName == null || originalName.trim().isEmpty()) {
            return ApiResponse.error(400, "文件名无效");
        }

        byte[] content;
        try {
            content = file.getBytes();
        } catch (IOException e) {
            return ApiResponse.error(500, "文件上传失败");
        }

        FileRecord record = new FileRecord();
        record.setDocId(docId);
        record.setOriginalName(originalName);
        record.setStoredName(generateStoredName(originalName));
        record.setContentType(file.getContentType());
        record.setFileSize((long) content.length);
        record.setFileData(content);
        record.setCreatedAt(LocalDateTime.now());

        fileMapper.insert(record);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", record.getId());
        data.put("docId", record.getDocId());
        data.put("originalName", record.getOriginalName());
        data.put("contentType", record.getContentType());
        data.put("fileSize", record.getFileSize());
        data.put("createdAt", record.getCreatedAt());

        return ApiResponse.success("上传成功", data);
    }

    public FileRecord getFileById(Long id) {
        return fileMapper.findById(id);
    }

    public ApiResponse<?> listByDocId(Long docId) {
        List<FileRecord> files = fileMapper.findByDocId(docId);
        return ApiResponse.success(files);
    }

    public ApiResponse<?> listAll() {
        List<FileRecord> files = fileMapper.findAll();
        return ApiResponse.success(files);
    }

    private String generateStoredName(String originalName) {
        String extension = "";
        int dotIndex = originalName.lastIndexOf('.');
        if (dotIndex >= 0 && dotIndex < originalName.length() - 1) {
            extension = originalName.substring(dotIndex);
        }
        return UUID.randomUUID().toString().replace("-", "") + extension;
    }
}
