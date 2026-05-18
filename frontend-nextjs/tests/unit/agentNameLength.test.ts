import { describe, expect, it } from "vitest";
import {
	getAgentNameDisplayWidth,
	trimToAgentNameMaxDisplayWidth,
} from "../../src/lib/agentNameLength";

describe("agent name display width", () => {
	it("counts ASCII as one display unit", () => {
		expect(getAgentNameDisplayWidth("AgentName1")).toBe(10);
		expect(trimToAgentNameMaxDisplayWidth("AgentName12")).toBe("AgentName1");
	});

	it("counts Chinese characters as two display units", () => {
		expect(getAgentNameDisplayWidth("ABCDE")).toBe(5);
		expect(trimToAgentNameMaxDisplayWidth("ABCDEFGHIJKLMN")).toBe("ABCDEFGHIJ");
	});

	it("handles mixed ASCII and Chinese display width", () => {
		expect(getAgentNameDisplayWidth("abcde")).toBe(5);
		expect(trimToAgentNameMaxDisplayWidth("abcdefghijk")).toBe("abcdefghij");
	});

	it("counts wide symbols consistently with backend East Asian width", () => {
		expect(getAgentNameDisplayWidth("⌚⌚⌚⌚⌚")).toBe(10);
		expect(trimToAgentNameMaxDisplayWidth("⌚⌚⌚⌚⌚⌚")).toBe("⌚⌚⌚⌚⌚");
	});
});
