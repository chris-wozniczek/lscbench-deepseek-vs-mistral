package com.noteforge.platform.service;

import com.noteforge.platform.dto.ApiResponse;
import com.noteforge.platform.dto.LinkPreviewRequest;
import com.noteforge.platform.entity.LinkPreview;
import com.noteforge.platform.mapper.LinkPreviewMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class LinkPreviewService {

    private static final int TIMEOUT_MILLIS = 10000;

    private static final Pattern TITLE_PATTERN =
            Pattern.compile("<title[^>]*>(.*?)</title>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);

    private static final Pattern META_TAG_PATTERN =
            Pattern.compile("<meta\\b((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", Pattern.CASE_INSENSITIVE);

    private static final Pattern LINK_TAG_PATTERN =
            Pattern.compile("<link\\b((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", Pattern.CASE_INSENSITIVE);

    private static final Pattern ATTRIBUTE_PATTERN =
            Pattern.compile("([a-zA-Z_:][-a-zA-Z0-9_:.]*)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s\"'>]+))");

    @Autowired
    private LinkPreviewMapper linkPreviewMapper;

    public ApiResponse<?> generatePreview(LinkPreviewRequest request, Long userId) {
        String url = request.getUrl();
        if (url == null || (!url.startsWith("http://") && !url.startsWith("https://"))) {
            return ApiResponse.error(400, "URL必须以http://或https://开头");
        }

        LinkPreview preview = new LinkPreview();
        preview.setUrl(url);
        preview.setOwnerId(userId);
        preview.setCreatedAt(LocalDateTime.now());

        try {
            String html = readDocument(url);
            preview.setTitle(extractTitle(html));
            preview.setDescription(extractMetaContent(html, "description"));
            preview.setFaviconUrl(extractFavicon(html));

            linkPreviewMapper.insert(preview);
            return ApiResponse.success("预览生成成功", preview);
        } catch (Exception e) {
            preview.setTitle(null);
            preview.setDescription(null);
            preview.setFaviconUrl(null);
            try {
                linkPreviewMapper.insert(preview);
            } catch (Exception ignored) {
                // The failed-preview record is best effort; the response must still be returned.
            }
            return ApiResponse.success("预览生成失败", preview);
        }
    }

    private String readDocument(String url) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(TIMEOUT_MILLIS);
            connection.setReadTimeout(TIMEOUT_MILLIS);
            connection.setRequestProperty("User-Agent", "Mozilla/5.0 (compatible; NoteForgeLinkPreview/1.0)");
            connection.setRequestProperty("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");

            StringBuilder document = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                char[] buffer = new char[4096];
                int read;
                while ((read = reader.read(buffer)) != -1) {
                    document.append(buffer, 0, read);
                }
            }
            return document.toString();
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private String extractTitle(String html) {
        Matcher matcher = TITLE_PATTERN.matcher(html);
        if (matcher.find()) {
            return matcher.group(1).trim();
        }
        return null;
    }

    private String extractMetaContent(String html, String metaName) {
        Matcher tagMatcher = META_TAG_PATTERN.matcher(html);
        while (tagMatcher.find()) {
            String attributes = tagMatcher.group(1);
            String name = getAttribute(attributes, "name");
            if (name != null && name.trim().equalsIgnoreCase(metaName)) {
                String content = getAttribute(attributes, "content");
                return content != null ? content.trim() : null;
            }
        }
        return null;
    }

    private String extractFavicon(String html) {
        Matcher tagMatcher = LINK_TAG_PATTERN.matcher(html);
        while (tagMatcher.find()) {
            String attributes = tagMatcher.group(1);
            String rel = getAttribute(attributes, "rel");
            if (rel == null) {
                continue;
            }
            for (String token : rel.trim().split("\\s+")) {
                if (token.equalsIgnoreCase("icon")) {
                    String href = getAttribute(attributes, "href");
                    return href != null ? href.trim() : null;
                }
            }
        }
        return null;
    }

    private String getAttribute(String attributes, String attributeName) {
        Matcher matcher = ATTRIBUTE_PATTERN.matcher(attributes);
        while (matcher.find()) {
            if (matcher.group(1).equalsIgnoreCase(attributeName)) {
                String value = matcher.group(2);
                if (value == null) {
                    value = matcher.group(3);
                }
                if (value == null) {
                    value = matcher.group(4);
                }
                return value;
            }
        }
        return null;
    }
}
