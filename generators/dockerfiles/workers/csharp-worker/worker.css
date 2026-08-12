using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using System;
using System.IO;
using System.Threading;

const string ScriptPath = "/tmp/invocation.csx";
const string TriggerPath = "/tmp/run.trigger";
const int PollIntervalMs = 50;

Console.WriteLine("Worker started.");

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
        var code = await File.ReadAllTextAsync(ScriptPath);

        var options = ScriptOptions.Default
            .WithImports(
                "System",
                "System.IO",
                "System.Linq",
                "System.Collections.Generic",
                "System.Threading",
                "System.Threading.Tasks"
            );

        await CSharpScript.RunAsync(code, options);

        Console.WriteLine("Script completed successfully");
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine("Script failed:");
        Console.Error.WriteLine(ex);
    }
}