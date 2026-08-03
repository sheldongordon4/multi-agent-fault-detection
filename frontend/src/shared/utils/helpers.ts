export type FormErrors = Partial<Record<string, string[]>>;

// Map Axios error responses into field-based errors for forms
export function mapAxiosErrorToFieldErrors(error: any): FormErrors {
    const toField = (key: string, msg: string): FormErrors => ({
        [key]: [msg],
    });

    // Network or request-level errors
    if (!error?.response) {
        if (
            error?.code === "NETWORK_ERROR" ||
            error?.message?.includes("Network Error")
        ) {
            return toField(
                "general",
                "Network error. Please check your internet connection.",
            );
        }
        if (
            error?.code === "ECONNABORTED" ||
            error?.message?.includes("timeout")
        ) {
            return toField("general", "Request timeout. Please try again.");
        }
        return toField("general", "Connection error. Please try again.");
    }

    const { status, data } = error.response as { status: number; data?: any };

    // Common  validation structure: { errors: { field: [messages] } }
    const normalizedFieldErrors = (): FormErrors | null => {
        if (!data?.errors) return null;
        const fe: FormErrors = {};
        for (const [field, messages] of Object.entries<any>(data.errors)) {
            if (!messages) continue;
            fe[field] = Array.isArray(messages) ? messages : [String(messages)];
        }
        return fe;
    };

    switch (status) {
        case 400:
        case 422: {
            const fe = normalizedFieldErrors();
            if (fe && Object.keys(fe).length > 0) return fe;
            if (data?.message) return toField("general", data.message);
            if (data?.detail) return toField("general", data.detail);
            return toField(
                "general",
                "Invalid request. Please check your input.",
            );
        }
        case 401:
            // Auth-specific: surface under password to show near the form
            return toField(
                "password",
                data?.message || "Invalid credentials. Please try again.",
            );
        case 403:
            return toField("general", data?.message || "Access forbidden.");
        case 404:
            return toField("general", "Resource not found. Please try again.");
        case 409:
            // If backend sends a conflict without field details, attach to email by default for auth flows
            return toField(
                "email",
                data?.message ||
                    "Conflict error. This resource may already exist.",
            );
        case 429:
            return toField(
                "general",
                "Too many requests. Please try again later.",
            );
        case 500:
            return toField("general", "Server error. Please try again later.");
        case 502:
        case 503:
        case 504:
            return toField(
                "general",
                "Service temporarily unavailable. Please try again later.",
            );
        default:
            if (data?.message) return toField("general", data.message);
            if (data?.detail) return toField("general", data.detail);
            return toField(
                "general",
                `An error occurred (${status}). Please try again.`,
            );
    }
}
