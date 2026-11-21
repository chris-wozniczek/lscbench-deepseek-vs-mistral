package com.storyforge.platform.service;

import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

@Service
public class ScriptFetchService {

    public String fetchContent(String url) {
        if (url == null || url.isBlank()) {
            throw new IllegalArgumentException("URL不能为空");
        }
        try {
            URLConnection connection = new URL(url.trim()).openConnection();
            if (!(connection instanceof HttpURLConnection)) {
                throw new IllegalArgumentException("仅支持HTTP协议: " + url);
            }
            HttpURLConnection conn = (HttpURLConnection) connection;
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            conn.setRequestProperty("User-Agent", "Mozilla/5.0");
            int status = conn.getResponseCode();
            if (status != 200) {
                throw new IllegalArgumentException("获取剧本失败，响应状态码: " + status);
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                return reader.lines().collect(Collectors.joining("\n"));
            } finally {
                conn.disconnect();
            }
        } catch (java.io.IOException e) {
            throw new IllegalArgumentException("获取剧本失败: " + e.getMessage(), e);
        }
    }
}
