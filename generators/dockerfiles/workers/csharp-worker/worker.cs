using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using System;
using System.IO;
using System.Threading;

const string AppRoot = "/app";
const string ScriptPath = $"{AppRoot}/invocation.csx";
const string TriggerPath = "/tmp/run.trigger";
const int PollIntervalMs = 50;

Console.WriteLine("Worker started.");
Console.WriteLine($"Working directory: {Environment.CurrentDirectory}");
Console.WriteLine($"Script path: {ScriptPath}");
Console.WriteLine($"Script exists: {File.Exists(ScriptPath)}");

while (true)
{
    if (File.Exists(TriggerPath))
    {
        // Consume the trigger
        try
        {
            File.Delete(TriggerPath);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Failed to remove trigger: {ex}");
            Thread.Sleep(PollIntervalMs);
            continue;
        }

        if (File.Exists(ScriptPath))
        {
            await RunScriptAsync();
        }
        else
        {
            Console.Error.WriteLine($"{ScriptPath} does not exist.");
        }
    }

    Thread.Sleep(PollIntervalMs);
}

static async Task RunScriptAsync()
{
    Console.WriteLine($"Executing {ScriptPath}");

    try
    {
        // Make sure the script actually exists.
        if (!File.Exists(ScriptPath))
        {
            throw new FileNotFoundException(
                "Script file was not found.",
                ScriptPath);
        }

        // This is the DLL referenced by #r in invocation.csx.
        var libraryPath =
            $"{AppRoot}/lib/bin/Debug/net10.0/Org.OpenAPITools.dll";

        Console.WriteLine($"Library path: {libraryPath}");
        Console.WriteLine($"Library exists: {File.Exists(libraryPath)}");

        if (!File.Exists(libraryPath))
        {
            throw new FileNotFoundException(
                "Org.OpenAPITools.dll was not found.",
                libraryPath);
        }

        var code = await File.ReadAllTextAsync(ScriptPath);

        var options = ScriptOptions.Default
        .WithImports(
        "System",
        "System.IO",
        "System.Linq",
        "System.Collections.Generic",
        "System.Threading",
        "System.Threading.Tasks"
        )
        .AddReferences(
            MetadataReference.CreateFromFile(
                "/usr/share/dotnet/shared/Microsoft.AspNetCore.App/10.0.8/Microsoft.Extensions.Logging.Abstractions.dll"
        )
        )
        .WithFilePath(ScriptPath);

        await CSharpScript.RunAsync(code, options);

        Console.WriteLine("Script completed successfully");
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine("Script failed:");
        Console.Error.WriteLine(ex);
    }
}