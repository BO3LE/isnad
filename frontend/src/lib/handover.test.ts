import type { AgentManifest } from "./api";
import { availableTo, chainOrder, chainTail, describeStep, handover, runOrder, suggestNext, type StepLike } from "./handover";
import live from "@/test/catalog.json";

const catalog = live as unknown as AgentManifest[];
const step = (id: string, agentType: string, configuration: Record<string, unknown> = {}): StepLike => ({ id, agentType, configuration });
const edge = (source: string, target: string) => ({ id: `${source}-${target}`, source, target });

// The seeded "Blog → Video → YouTube" chain.
const research = step("r", "researcher", { topic: "Solar" });
const write = step("w", "writer", { format: "video_script" });
const video = step("v", "video");
const publish = step("p", "publisher", { platform: "youtube" });
const chain = [research, write, video, publish];
const links = [edge("r", "w"), edge("w", "v"), edge("v", "p")];

describe("handover — what crosses a connection", () => {
  it("names what the next step actually reads", () => {
    expect(handover("researcher", "writer", catalog)).toEqual(["notes", "sources"]);
    expect(handover("writer", "video", catalog)).toEqual(["title", "article"]);
    expect(handover("video", "publisher", catalog)).toEqual(["video"]);
    expect(handover("publisher", "email", catalog)).toEqual(["link"]);
  });

  it("is empty when the connection can't work — Email → Writer", () => {
    expect(handover("email", "writer", catalog)).toEqual([]);
  });
});

describe("where each value comes from", () => {
  it("Writer's notes come from Researcher", () => {
    const { sources, needs } = describeStep(write, chain, links, catalog);
    expect(sources.get("notes")).toMatchObject({ kind: "inherited", from: { agentTitle: "Researcher", outputTitle: "notes" } });
    expect(needs).toEqual([]);
  });

  it("Video reads Writer's article as its script", () => {
    const { sources } = describeStep(video, chain, links, catalog);
    expect(sources.get("script")).toMatchObject({ kind: "inherited", from: { agentTitle: "Writer", output: "article_md" } });
  });

  it("Publisher inherits the title from Writer two steps back, and the file from Video", () => {
    const { sources, needs } = describeStep(publish, chain, links, catalog);
    expect(sources.get("title")).toMatchObject({ kind: "inherited", from: { agentTitle: "Writer" } });
    expect(sources.get("file_path")).toMatchObject({ kind: "inherited", from: { agentTitle: "Video", outputTitle: "video" } });
    expect(sources.get("privacy")).toEqual({ kind: "default" });
    expect(needs).toEqual([]);
  });

  it("a typed value overrides what an earlier step would hand on", () => {
    const own = step("p", "publisher", { title: "My own title" });
    const { sources } = describeStep(own, [research, write, video, own], links, catalog);
    expect(sources.get("title")).toEqual({ kind: "own" });
  });

  it("an empty value still inherits — clearing gives control back", () => {
    const cleared = step("p", "publisher", { title: "" });
    const { sources } = describeStep(cleared, [research, write, video, cleared], links, catalog);
    expect(sources.get("title")).toMatchObject({ kind: "inherited" });
  });

  it("Image uses the article title when its own prompt is empty", () => {
    const image = step("i", "image");
    const { sources } = describeStep(image, [write, image], [edge("w", "i")], catalog);
    expect(sources.get("prompt")).toMatchObject({ kind: "inherited", from: { agentTitle: "Writer", outputTitle: "title" } });
  });
});

describe("what a step still needs", () => {
  it("Writer on its own needs a Researcher", () => {
    const lonely = step("w", "writer");
    expect(describeStep(lonely, [lonely], [], catalog).needs).toEqual(["Needs a Researcher before this step"]);
  });

  it("wired backwards, Writer still needs a Researcher", () => {
    const email = step("e", "email", { recipients: ["demo@gp.local"] });
    const lonely = step("w", "writer");
    expect(describeStep(lonely, [email, lonely], [edge("e", "w")], catalog).needs).toEqual(["Needs a Researcher before this step"]);
  });

  it("Publisher without a Video needs one", () => {
    const alone = step("p", "publisher");
    expect(describeStep(alone, [research, write, alone], [edge("r", "w"), edge("w", "p")], catalog).needs).toEqual([
      "Needs a Video before this step",
    ]);
  });

  it("a value the user could type says so", () => {
    const image = step("i", "image");
    expect(describeStep(image, [image], [], catalog).needs).toEqual(["Missing: prompt — or add a Writer before it"]);
  });

  it("a required setting nothing can supply is left to the settings check", () => {
    const bare = step("r", "researcher");
    expect(describeStep(bare, [bare], [], catalog).needs).toEqual([]);
  });
});

describe("run order", () => {
  it("follows the connections, not the order steps were added", () => {
    expect(runOrder(["p", "v", "w", "r"], links)).toEqual(["r", "w", "v", "p"]);
  });

  it("a later step's output wins", () => {
    // Two writers in a row: the second one's title is what arrives.
    const first = step("w1", "writer");
    const second = step("w2", "writer");
    const image = step("i", "image");
    const available = availableTo("i", [first, second, image], [edge("w1", "w2"), edge("w2", "i")], catalog);
    expect(available.get("title")?.stepId).toBe("w2");
  });
});

describe("the palette's order and suggestions", () => {
  it("lists agents in the order a chain is built", () => {
    expect(chainOrder(catalog).map((a) => a.name)).toEqual(["researcher", "writer", "image", "video", "publisher", "email"]);
  });

  it("an empty canvas starts with Researcher", () => {
    expect(suggestNext(null, catalog).map((s) => s.agent.name)).toEqual(["researcher"]);
  });

  it("after Researcher comes Writer, because Writer needs the notes", () => {
    expect(suggestNext("researcher", catalog)).toEqual([expect.objectContaining({ reason: "Takes notes and sources from Researcher" })]);
    expect(suggestNext("researcher", catalog)[0]?.agent.name).toBe("writer");
  });

  it("after Writer, the steps that need its article come first", () => {
    const names = suggestNext("writer", catalog).map((s) => s.agent.name);
    expect(names[0]).toBe("video");
    expect(names).toHaveLength(3);
  });

  it("after Video comes Publisher", () => {
    expect(suggestNext("video", catalog).map((s) => s.agent.name)).toEqual(["publisher"]);
  });

  it("adds after the selected step, else the end of the chain", () => {
    expect(chainTail(["r", "w", "v", "p"], links, null)).toBe("p");
    expect(chainTail(["r", "w", "v", "p"], links, "w")).toBe("w");
    expect(chainTail([], [], null)).toBeNull();
  });
});
