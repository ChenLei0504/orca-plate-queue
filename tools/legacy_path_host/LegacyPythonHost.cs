// Isolated verification host. It has no printer networking or SDK dependency.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;

class LegacyPythonHost {
    [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern bool SetDllDirectory(string path);
    [DllImport("python312",CallingConvention=CallingConvention.Cdecl)]
    static extern void Py_SetPythonHome(IntPtr home);
    [DllImport("python312",CallingConvention=CallingConvention.Cdecl)]
    static extern void Py_Initialize();
    [DllImport("python312",CallingConvention=CallingConvention.Cdecl)]
    static extern int PyRun_SimpleString(byte[] script);
    [DllImport("python312",CallingConvention=CallingConvention.Cdecl)]
    static extern int Py_FinalizeEx();
    static int Main(string[] args) {
        if(args.Length!=2)return 2;
        var home=Marshal.StringToHGlobalUni(args[0]);
        try {
            if(!SetDllDirectory(args[0]))return 3;
            Py_SetPythonHome(home);Py_Initialize();
            var script=Encoding.UTF8.GetBytes(File.ReadAllText(args[1],Encoding.UTF8)+"\0");
            int result=PyRun_SimpleString(script);
            int finalize=Py_FinalizeEx();
            return result==0&&finalize==0?0:1;
        } finally {Marshal.FreeHGlobal(home);}
    }
}
